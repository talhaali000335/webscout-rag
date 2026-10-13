"""Human-in-the-loop sign-in.

When the scraper hits a login wall / captcha, the worker calls wait_for_user().
The job status becomes "needs_login" and the web UI opens a live view of the
server-side browser (screenshots over a WebSocket; clicks/typing are sent back).
When the user presses "Continue", the scrape resumes with their cookies.
"""
import asyncio
from dataclasses import dataclass, field

from .config import settings

# job_id -> LoginSession (lives in memory: the worker and the API share one process)
SESSIONS: dict = {}

ALLOWED_KEYS = {
    "Enter", "Backspace", "Tab", "Escape", "Delete", "Home", "End", "PageUp", "PageDown",
    "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Space",
}


@dataclass
class LoginSession:
    page: object
    reason: str
    done: asyncio.Event = field(default_factory=asyncio.Event)
    cancelled: bool = False


async def wait_for_user(redis, job_id: str, page, reason: str) -> bool:
    key = f"job:{job_id}"
    s = LoginSession(page=page, reason=reason)
    SESSIONS[job_id] = s
    await redis.hset(key, mapping={"status": "needs_login", "stage": "waiting_for_user",
                                   "login_reason": reason})
    try:
        await asyncio.wait_for(s.done.wait(), settings.login_timeout)
        return not s.cancelled
    except asyncio.TimeoutError:
        return False
    finally:
        SESSIONS.pop(job_id, None)
        await redis.hset(key, mapping={"status": "running", "stage": "scraping"})


async def apply_event(page, ev: dict) -> None:
    """Forward one user input event (from the browser view) to the real page."""
    t = ev.get("t")
    if t == "click":
        x = max(0, min(float(ev["x"]), 4000))
        y = max(0, min(float(ev["y"]), 4000))
        await page.mouse.click(x, y)
    elif t == "type":
        text = str(ev.get("text", ""))[:300]
        if text:
            await page.keyboard.insert_text(text)
    elif t == "key":
        key = ev.get("key")
        if key in ALLOWED_KEYS:
            await page.keyboard.press("Space" if key == "Space" else key)
    elif t == "scroll":
        dy = max(-1500, min(float(ev.get("dy", 0)), 1500))
        await page.mouse.wheel(0, dy)
