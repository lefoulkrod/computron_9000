"""Fetch a web page over plain HTTP and return it as readable text."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import mimetypes
from pathlib import Path

import aiohttp
import trafilatura

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 20
_SAVE_DIR = Path("/tmp")

# Largest amount of page text returned inline; the rest stays in the file.
_INLINE_BUDGET = 20_000

# A real browser UA — bare HTTP clients are blocked by many sites outright.
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Substrings that mark an anti-bot interstitial rather than real content.
_BOT_WALL_MARKERS = (
    "just a moment...",
    "cf-browser-verification",
    "attention required! | cloudflare",
    "captcha-delivery",
    "/cdn-cgi/challenge-platform",
    "please enable javascript and cookies",
)

_BROWSER_HINT = "The page may need a full browser to load."

# Text formats served as-is — already readable, no HTML extraction needed.
_RAW_TEXT_TYPES = ("text/plain", "text/markdown", "text/x-markdown")


def _looks_like_bot_wall(html: str) -> bool:
    """True when *html* looks like an anti-bot challenge page."""
    lowered = html[:4000].lower()
    return any(marker in lowered for marker in _BOT_WALL_MARKERS)


def _extract_markdown(html: str) -> str | None:
    """Extract the main content of *html* as markdown, or None if there is none."""
    return trafilatura.extract(
        html,
        output_format="markdown",
        include_formatting=True,
        include_links=True,
        include_comments=False,
        include_tables=True,
    )


async def fetch_url(url: str) -> str:
    """Fetch a web page over HTTP and return its readable text — no browser.

    Use this to read a page when you already have its URL. Page content is
    returned inline as markdown, and the full page is always saved to a file;
    when the inline text is marked truncated, read the rest from that saved
    file. Non-web content (PDFs, images, archives) is saved to a file and its
    path is returned instead of inline text.

    When this returns a blocked or failed message, the page needs a full
    browser — it likely requires JavaScript rendering or interactive
    navigation.

    Args:
        url: The page URL to fetch (http/https).

    Returns:
        Formatted string: a header with the URL, HTTP status, saved file path
        and size, followed by the page text. Returns a plain message when the
        fetch fails or is blocked by bot detection.
    """
    headers = {"User-Agent": _USER_AGENT}
    timeout = aiohttp.ClientTimeout(total=_TIMEOUT_SECONDS)

    try:
        async with (
            aiohttp.ClientSession(timeout=timeout, headers=headers) as session,
            session.get(url, allow_redirects=True) as resp,
        ):
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            is_raw_text = any(t in content_type for t in _RAW_TEXT_TYPES)
            # Empty content type — assume a web page and try to parse it.
            is_webpage = (
                "html" in content_type or is_raw_text or content_type == ""
            )
            text = await resp.text() if is_webpage else ""
            data = b"" if is_webpage else await resp.read()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.warning("fetch_url failed for %r: %s", url, exc)
        return f"Could not fetch {url}: {exc}. {_BROWSER_HINT}"

    if status >= 400:
        logger.info("fetch_url got HTTP %d for %r", status, url)
        return (
            f"Fetching {url} returned HTTP {status} — the page may be "
            f"blocking automated requests. {_BROWSER_HINT}"
        )

    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]

    # Non-web content (PDFs, images, archives): save the raw file and return
    # its path so the agent can open it with whatever tool suits the format.
    if not is_webpage:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ".bin"
        dest = _SAVE_DIR / f"fetch_{digest}{ext}"
        try:
            dest.write_bytes(data)
        except OSError:
            logger.exception("fetch_url could not save the file from %r", url)
            return f"Could not save the downloaded file from {url}."
        return (
            f"[Fetched: {url} | HTTP {status} | {content_type} | "
            f"{len(data):,} bytes | saved: {dest}]"
        )

    if _looks_like_bot_wall(text):
        logger.info("fetch_url hit a bot wall for %r", url)
        return (
            f"{url} served an anti-bot challenge page instead of content. "
            f"{_BROWSER_HINT}"
        )

    if is_raw_text:
        full_content = text.strip()
    else:
        # trafilatura extraction is CPU-bound — keep it off the event loop.
        extracted = await asyncio.to_thread(_extract_markdown, text)
        full_content = (extracted or "").strip()

    if not full_content:
        return (
            f"No readable content could be extracted from {url}. "
            f"{_BROWSER_HINT}"
        )

    # Save the full content so large pages can be read from the file rather
    # than pulled entirely inline.
    dest = _SAVE_DIR / f"fetch_{digest}.md"
    try:
        dest.write_text(full_content, encoding="utf-8")
        size = dest.stat().st_size
    except OSError:
        logger.exception("fetch_url could not save content for %r", url)
        dest = None
        size = len(full_content.encode("utf-8"))

    truncated = len(full_content) > _INLINE_BUDGET
    inline = full_content[:_INLINE_BUDGET] if truncated else full_content

    saved = f" | saved: {dest}" if dest is not None else " | save failed"
    trunc = " | truncated" if truncated else ""
    header = f"[Fetched: {url} | HTTP {status} | {size:,} bytes{saved}{trunc}]"
    if truncated and dest is not None:
        header += (
            f"\n[Showing the first {_INLINE_BUDGET:,} chars — the full page "
            f"is saved at {dest}.]"
        )
    return f"{header}\n\n{inline}"


__all__ = ["fetch_url"]
