"""Universal scraper.

Strategy (cheapest first):
  1. Plain HTTP fetch (httpx)  -> fast, tiny memory
  2. Playwright (real Chromium) -> for JavaScript-heavy / bot-protected pages
Both go through the same BeautifulSoup extractor.

If the site shows a login / captcha / bot-check wall, the job pauses and the user
signs in (or solves the captcha) themselves in a live remote-browser view, then the
scrape resumes. Sessions (cookies) are saved per user + site so it's a one-time step.

Security: every request (including redirects) is checked so the scraper can
never be pointed at localhost / private networks / the AWS metadata endpoint.
"""
import asyncio
import ipaddress
import json
import re
import socket
import os
from pathlib import Path
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
MIN_GOOD_CHARS = 800
BLOCK_HINTS = (
    "captcha", "robot check", "are you a robot", "access denied",
    "verify you are human", "unusual traffic", "enable javascript",
    "enter the characters you see", "type the characters", "press & hold",
    "checking your browser", "just a moment",
)
LOGIN_URL = re.compile(r"/(login|log-in|signin|sign-in|ap/signin|account/login|auth)(/|\?|$)", re.I)
VIEW_W, VIEW_H = 1024, 720


class ScrapeError(Exception):
    pass


@dataclass
class Page:
    url: str
    title: str
    sections: list  # list[(heading, text)]
    method: str

    @property
    def text_len(self) -> int:
        return sum(len(t) for _, t in self.sections)


# ----------------------------------------------------------------- safety
@lru_cache(maxsize=512)
def _check_host(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise ScrapeError(f"Could not resolve host: {host}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            raise ScrapeError("Blocked: URL points to a private/internal address")


def assert_public_url(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ScrapeError("Only http(s) URLs are allowed")
    _check_host(p.hostname)


def normalize_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    p = urlparse(url)
    if not p.hostname or "." not in p.hostname:
        raise ScrapeError("That doesn't look like a valid URL")
    return url


# ------------------------------------------------------------- extraction
_NOISE_TAGS = ["script", "style", "noscript", "svg", "iframe", "form", "nav",
               "footer", "aside", "template", "button", "select", "option"]


def _flatten(obj, prefix="", out=None, depth=0):
    """Turn JSON-LD (product/article data) into readable 'key: value' lines."""
    out = [] if out is None else out
    if depth > 6:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.startswith("@") and k != "@type":
                continue
            if k in ("image", "logo", "thumbnailUrl", "url", "sameAs"):
                continue
            _flatten(v, f"{prefix}{k}.", out, depth + 1)
    elif isinstance(obj, list):
        for v in obj[:20]:
            _flatten(v, prefix, out, depth + 1)
    elif obj not in (None, ""):
        out.append(f"{prefix[:-1]}: {obj}")
    return out


def _jsonld_text(soup: BeautifulSoup) -> str:
    lines = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        lines.extend(_flatten(data))
    return "\n".join(lines)[:6000]


def extract(html: str, url: str) -> Page:
    soup = BeautifulSoup(html, "lxml")
    title = (soup.title.string.strip() if soup.title and soup.title.string else "") or url

    meta = []
    for key in ("description", "og:title", "og:description"):
        m = soup.find("meta", attrs={"name": key}) or soup.find("meta", attrs={"property": key})
        if m and m.get("content"):
            meta.append(f"{key}: {m['content'].strip()}")
    jsonld = _jsonld_text(soup)

    for t in soup.find_all(_NOISE_TAGS):
        t.decompose()
    for t in soup.find_all(attrs={"class": re.compile(r"cookie|consent", re.I)}):
        t.decompose()

    root = soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"})
    if not root or len(root.get_text(" ", strip=True)) < 500:
        root = soup.body or soup

    # mark headings so we can split the page into sections afterwards
    for h in root.find_all(re.compile(r"^h[1-6]$")):
        txt = h.get_text(" ", strip=True)
        if txt:
            h.clear()
            h.append(f"\n\n#H# {txt}\n")

    raw = root.get_text("\n")
    seen, lines = set(), []
    for line in raw.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if len(line) < 2:
            continue
        if not line.startswith("#H#") and len(line) < 60:
            if line in seen:  # drop repeated UI labels ("Add to cart" x30)
                continue
            seen.add(line)
        lines.append(line)

    sections, heading, buf = [], title, []
    for line in lines:
        if line.startswith("#H# "):
            if buf:
                sections.append((heading, "\n".join(buf)))
            heading, buf = line[4:], []
        else:
            buf.append(line)
    if buf:
        sections.append((heading, "\n".join(buf)))

    head = []
    if meta:
        head.append("\n".join(meta))
    if jsonld:
        head.append(jsonld)
    if head:
        sections.insert(0, ("Page summary & structured data", "\n".join(head)))

    return Page(url=url, title=title[:200], sections=sections, method="")


# ---------------------------------------------------------------- fetching
async def _fetch_http(url: str) -> str:
    async def guard(request: httpx.Request):
        await asyncio.to_thread(assert_public_url, str(request.url))

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=20, event_hooks={"request": [guard]},
        headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
                 "Accept": "text/html,application/xhtml+xml"},
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        if "html" not in r.headers.get("content-type", "html"):
            raise ScrapeError("URL is not an HTML page")
        return r.text[:3_000_000]


def _looks_blocked(page: Page) -> bool:
    if page.text_len > 3000:
        return False
    blob = " ".join(t for _, t in page.sections).lower() + page.title.lower()
    return any(h in blob for h in BLOCK_HINTS)


def detect_wall(html: str, page_url: str, page: Page):
    """Returns a short reason string if this looks like a login / bot wall, else None."""
    if page.text_len > 3000:
        return None
    if _looks_blocked(page):
        return "The site is showing a bot check / captcha."
    soup = BeautifulSoup(html, "lxml")
    if soup.find("input", attrs={"type": "password"}):
        return "The site is asking you to sign in."
    if LOGIN_URL.search(urlparse(page_url).path or ""):
        return "The site redirected to a sign-in page."
    return None


def session_file(client_id: str, url: str) -> Path | None:
    """Per-user + per-site file where we keep cookies after a successful sign-in."""
    from hashlib import sha1
    from .config import settings
    if not client_id:
        return None
    host = (urlparse(url).hostname or "").removeprefix("www.")
    d = Path(settings.data_dir) / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{sha1(client_id.encode()).hexdigest()[:12]}_{sha1(host.encode()).hexdigest()[:12]}.json"


def forget_sessions(client_id: str) -> int:
    from hashlib import sha1
    from .config import settings
    if not client_id:
        return 0
    prefix = sha1(client_id.encode()).hexdigest()[:12] + "_"
    d = Path(settings.data_dir) / "sessions"
    n = 0
    if d.exists():
        for p in d.glob(prefix + "*.json"):
            p.unlink(missing_ok=True)
            n += 1
    return n


async def _settle(page):
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    for _ in range(4):  # trigger lazy-loaded sections
        await page.mouse.wheel(0, 2500)
        await page.wait_for_timeout(350)


async def _fetch_playwright(url: str, state_path: Path | None, ask_user, login_first: bool):
    """Returns (html, used_human). ask_user(page, reason) -> bool pauses for the human."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=[
            "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-extensions",
            "--renderer-process-limit=1", "--js-flags=--max-old-space-size=256"])
        try:
            ctx_args = dict(user_agent=UA, locale="en-US", viewport={"width": VIEW_W, "height": VIEW_H})
            if state_path and state_path.exists():
                ctx_args["storage_state"] = str(state_path)
            ctx = await browser.new_context(**ctx_args)
            page = await ctx.new_page()
            flags = {"human": False}

            async def guard(route):
                req = route.request
                if req.resource_type in ("media", "font"):
                    return await route.abort()
                # images are only needed while a human is looking at the page (captchas!)
                if req.resource_type == "image" and not (ask_user and flags["human"]):
                    return await route.abort()
                try:
                    await asyncio.to_thread(assert_public_url, req.url)
                except ScrapeError:
                    return await route.abort()
                await route.continue_()

            await page.route("**/*", guard)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await _settle(page)
            html = await page.content()

            reason = None
            if login_first:
                reason = "You asked to sign in first. Log in, then press Continue."
            else:
                reason = detect_wall(html, page.url, extract(html, page.url))

            used_human = False
            if reason and ask_user:
                # reload with images enabled so the human can see captchas / buttons
                flags["human"] = True
                try:
                    await page.reload(wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass
                ok = await ask_user(page, reason)
                if not ok:
                    raise ScrapeError("Sign-in was cancelled or timed out.")
                used_human = True
                flags["human"] = False
                # the human may have wandered off; go back to the page we want
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await _settle(page)
                html = await page.content()
                if state_path:
                    await ctx.storage_state(path=str(state_path))
                    os.chmod(state_path, 0o600)
            elif state_path and state_path.exists():
                await ctx.storage_state(path=str(state_path))  # refresh cookies
            return html[:3_000_000], used_human
        finally:
            await browser.close()


async def scrape(url: str, client_id: str = "", ask_user=None, login_first: bool = False) -> Page:
    await asyncio.to_thread(assert_public_url, url)
    state_path = session_file(client_id, url)

    best: Page | None = None
    # A saved login (or "sign in first") means the plain HTTP fetch would see the logged-out page.
    skip_http = login_first or bool(state_path and state_path.exists())
    if not skip_http:
        try:
            html = await _fetch_http(url)
            page = extract(html, url)
            page.method = "http"
            if page.text_len >= MIN_GOOD_CHARS and not _looks_blocked(page):
                return page
            best = page
        except ScrapeError:
            raise
        except Exception:
            pass  # 403 / timeout / etc -> try the real browser

    try:
        html, used_human = await _fetch_playwright(url, state_path, ask_user, login_first)
        page = extract(html, url)
        page.method = "playwright+login" if used_human else "playwright"
        if page.text_len > (best.text_len if best else 0):
            best = page
    except ScrapeError:
        raise
    except Exception as e:
        if not best:
            raise ScrapeError(f"Could not load the page: {type(e).__name__}")

    if not best or best.text_len < 200:
        raise ScrapeError("Page had almost no readable text (it may be blocking bots or need a login).")
    if _looks_blocked(best):
        raise ScrapeError("The site still shows a bot-check / captcha page instead of real content.")
    return best
