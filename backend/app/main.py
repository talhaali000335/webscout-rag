import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import interactive, rag
from .chunking import chunk_sections
from .config import settings
from .scraper import ScrapeError, forget_sessions, normalize_url, scrape

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")

redis: aioredis.Redis = None  # set in lifespan


# ------------------------------------------------------------ job worker
async def run_job(job_id: str):
    key = f"job:{job_id}"
    job = await redis.hgetall(key)
    url, cid = job["url"], job["cid"]
    try:
        await redis.hset(key, mapping={"status": "running", "stage": "scraping"})
        async def ask_user(page, reason):
            return await interactive.wait_for_user(redis, job_id, page, reason)

        page = await scrape(url, client_id=job.get("client", ""), ask_user=ask_user,
                            login_first=job.get("login_first") == "1")

        await redis.hset(key, mapping={"stage": "chunking"})
        chunks = chunk_sections(page.sections, settings.chunk_chars, settings.chunk_overlap)
        if not chunks:
            raise ScrapeError("No text could be extracted from this page")

        await redis.hset(key, mapping={"stage": "embedding"})
        n = await rag.index_chunks(cid, url, page.title, chunks)

        meta = {"url": url, "title": page.title, "chunks": n, "method": page.method,
                "indexed_at": int(time.time())}
        await redis.hset(f"page:{cid}", mapping=meta)
        await redis.expire(f"page:{cid}", settings.cache_ttl)
        await redis.hset(key, mapping={"status": "ready", "stage": "done",
                                       "title": page.title, "chunks": n, "method": page.method})
    except ScrapeError as e:
        await redis.hset(key, mapping={"status": "error", "error": str(e)})
    except Exception as e:  # never let one bad job kill the worker
        log.exception("job failed")
        await redis.hset(key, mapping={"status": "error", "error": f"Internal error: {type(e).__name__}"})


async def worker():
    """Tiny Redis-backed queue: one job at a time (keeps RAM low on a t2.micro)."""
    while True:
        try:
            item = await redis.blpop("jobs", timeout=5)
            if item:
                await run_job(item[1])
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("worker error")
            await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    task = asyncio.create_task(worker())
    asyncio.create_task(asyncio.to_thread(rag.warmup))  # load models in background
    yield
    task.cancel()
    await redis.aclose()


app = FastAPI(title="WebScout-RAG", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"], allow_headers=["*"])


# ----------------------------------------------------------- rate limiter
async def rate_limit(request: Request):
    fwd = request.headers.get("x-forwarded-for", "")
    ip = fwd.split(",")[0].strip() or (request.client.host if request.client else "?")
    key = f"rl:{ip}:{int(time.time() // 60)}"
    n = await redis.incr(key)
    if n == 1:
        await redis.expire(key, 70)
    if n > settings.rate_limit_per_min:
        raise HTTPException(429, "Too many requests, slow down a little.")


# -------------------------------------------------------------- schemas
class IngestIn(BaseModel):
    url: str = Field(min_length=3, max_length=2000)
    force: bool = False
    login_first: bool = False   # open a browser so the user can sign in BEFORE scraping


class Turn(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    collection_id: str = Field(min_length=4, max_length=32)
    question: str = Field(min_length=1, max_length=1000)
    history: list[Turn] = []


# ------------------------------------------------------------ endpoints
@app.get("/api/health")
async def health():
    return {"ok": True, "redis": await redis.ping()}


@app.post("/api/ingest", dependencies=[Depends(rate_limit)])
async def ingest(body: IngestIn, request: Request):
    try:
        url = normalize_url(body.url)
    except ScrapeError as e:
        raise HTTPException(400, str(e))
    cid = rag.collection_id(url)

    client = request.headers.get("x-client-id", "")[:64]
    if not body.force and not body.login_first and await redis.exists(f"page:{cid}"):
        page = await redis.hgetall(f"page:{cid}")
        return {"job_id": None, "collection_id": cid, "status": "ready", "cached": True,
                "title": page.get("title"), "chunks": int(page.get("chunks", 0)), "url": url}

    job_id = uuid.uuid4().hex[:12]
    await redis.hset(f"job:{job_id}", mapping={
        "url": url, "cid": cid, "status": "queued", "stage": "queued",
        "client": client, "login_first": "1" if body.login_first else "0"})
    await redis.expire(f"job:{job_id}", 86400)
    await redis.rpush("jobs", job_id)
    return {"job_id": job_id, "collection_id": cid, "status": "queued", "cached": False, "url": url}


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    job = await redis.hgetall(f"job:{job_id}")
    if not job:
        raise HTTPException(404, "Unknown job")
    return job


@app.post("/api/chat", dependencies=[Depends(rate_limit)])
async def chat(body: ChatIn):
    if not await redis.exists(f"page:{body.collection_id}"):
        raise HTTPException(404, "page_not_indexed")
    try:
        return await rag.answer(body.collection_id, body.question,
                                [t.model_dump() for t in body.history])
    except rag.LLMError as e:
        raise HTTPException(503, str(e))
    except Exception:
        log.exception("chat failed")
        raise HTTPException(500, "Something went wrong while answering. Try again.")


# ------------------------------------------- human sign-in (remote browser)
async def _check_owner(job_id: str, client: str) -> bool:
    job = await redis.hgetall(f"job:{job_id}")
    return bool(job) and bool(client) and job.get("client") == client


@app.post("/api/jobs/{job_id}/resume")
async def job_resume(job_id: str, request: Request):
    if not await _check_owner(job_id, request.headers.get("x-client-id", "")):
        raise HTTPException(403, "Not your job")
    s = interactive.SESSIONS.get(job_id)
    if not s:
        raise HTTPException(409, "This job is not waiting for sign-in")
    s.done.set()
    return {"ok": True}


@app.post("/api/jobs/{job_id}/cancel")
async def job_cancel(job_id: str, request: Request):
    if not await _check_owner(job_id, request.headers.get("x-client-id", "")):
        raise HTTPException(403, "Not your job")
    s = interactive.SESSIONS.get(job_id)
    if s:
        s.cancelled = True
        s.done.set()
    return {"ok": True}


@app.delete("/api/sessions")
async def forget(request: Request):
    """Delete every saved site login (cookies) belonging to this browser."""
    return {"deleted": forget_sessions(request.headers.get("x-client-id", ""))}


@app.websocket("/api/ws/browser/{job_id}")
async def ws_browser(ws: WebSocket, job_id: str, client: str = ""):
    s = interactive.SESSIONS.get(job_id)
    if not s or not await _check_owner(job_id, client):
        await ws.close(code=4403)
        return
    await ws.accept()
    page = s.page

    async def sender():
        last = b""
        while True:
            try:
                img = await page.screenshot(type="jpeg", quality=55)
                if img != last:
                    await ws.send_bytes(img)
                    last = img
                await ws.send_json({"url": page.url, "reason": s.reason})
            except Exception:
                if page.is_closed():
                    return
            await asyncio.sleep(0.4)

    task = asyncio.create_task(sender())
    try:
        while True:
            ev = await ws.receive_json()
            try:
                await interactive.apply_event(page, ev)
            except Exception:
                pass
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        task.cancel()
