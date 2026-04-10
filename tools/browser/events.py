"""Browser tool event emission helpers.

This module provides a single ``_emit_screenshot`` function that captures a
JPEG screenshot from a Playwright page and publishes it as a
``BrowserScreenshotPayload`` event for the UI.

All screenshot emission flows funnel through ``_emit_screenshot``:

- **Progressive** — ``request_progressive_screenshot`` queues a throttled,
  non-blocking capture via ``_ScreenshotEmitter`` during interactions (mouse
  movement, typing, scrolling).
- **Post-tool** — ``emit_screenshot_after`` decorator calls
  ``_emit_screenshot`` once after a tool returns a result with a page view.
- **Ad-hoc** — ``javascript.py`` calls ``emit_screenshot`` directly after
  JS evaluation.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.async_api import Page

from tools.browser.core import get_browser

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Core screenshot capture + publish
# ---------------------------------------------------------------------------


async def _emit_screenshot(page: Page) -> None:
    """Capture a JPEG screenshot from *page* and publish it as a browser event.

    This is the single code path for all screenshot emission.  Uses JPEG at
    reduced quality for fast encoding and small payloads.
    """
    from sdk.events import (
        AgentEvent,
        BrowserScreenshotPayload,
        publish_event,
    )

    screenshot_bytes = await page.screenshot(type="jpeg", quality=55)
    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")

    url = getattr(page, "url", "")
    try:
        title = await page.title()
    except Exception:  # noqa: BLE001
        title = ""

    publish_event(AgentEvent(payload=BrowserScreenshotPayload(
        type="browser_screenshot",
        url=url,
        title=title,
        screenshot=screenshot_base64,
    )))


async def emit_screenshot(page: Page) -> None:
    """Public wrapper around ``_emit_screenshot`` for use by other modules.

    Swallows all exceptions so callers never fail due to screenshot capture.
    """
    try:
        await _emit_screenshot(page)
    except Exception as exc:  # noqa: BLE001
        url = getattr(page, "url", "unknown")
        closed = page.is_closed() if hasattr(page, "is_closed") else "?"
        logger.warning(
            "Screenshot failed (page=%s, closed=%s)", url, closed,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Throttled background screenshot emitter
# ---------------------------------------------------------------------------

# Minimum interval between progressive screenshots (seconds).
# ~10 fps keeps the UI feeling live without saturating bandwidth.
_MIN_SCREENSHOT_INTERVAL_S: float = 0.1


class _ScreenshotEmitter:
    """Fire-and-forget, throttled screenshot emitter.

    Interaction helpers call ``request`` to signal that a screenshot would be
    useful.  The emitter coalesces rapid requests and captures at most once per
    ``_MIN_SCREENSHOT_INTERVAL_S`` seconds, running the capture in a background
    ``asyncio.Task`` so the caller never blocks.

    The background task uses a *latest-value-only* drain loop: after each
    capture it checks whether new requests arrived during the (potentially
    slow) screenshot and, if so, throttle-waits then captures again.  This
    guarantees at most **one** task is alive at a time and prevents
    backpressure from stacking up screenshot calls.
    """

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._last_emit: float = 0.0
        # The page to screenshot is stored per-request so the background task
        # always captures the most recently requested page.
        self._pending_page: Page | None = None
        # Monotonically increasing generation counter.  ``request()``
        # increments it; ``_run()`` compares against the value recorded
        # before capture to detect new requests that arrived mid-capture.
        self._generation: int = 0

    def request(self, page: Page) -> None:
        """Request a progressive screenshot.  Returns immediately.

        If a capture is already in-flight or was emitted recently, the request
        is coalesced so at most one capture runs per throttle window.

        Args:
            page: The Playwright page to screenshot.
        """
        self._pending_page = page
        self._generation += 1

        # If a background task is already running it will pick up the latest
        # pending page on its next loop iteration — no new task needed.
        if self._task is not None and not self._task.done():
            return

        self._task = asyncio.get_event_loop().create_task(self._run())

    async def _run(self) -> None:
        """Background drain loop: capture, then re-check for new requests.

        The loop exits when no new requests arrived during the most recent
        capture.  This keeps exactly one task alive and avoids stacking
        screenshot calls when capture latency exceeds the request rate.
        """
        try:
            while True:
                # Respect throttle — if we emitted very recently, wait out the
                # remainder of the interval so we don't flood the UI.
                since = time.monotonic() - self._last_emit
                if since < _MIN_SCREENSHOT_INTERVAL_S:
                    await asyncio.sleep(_MIN_SCREENSHOT_INTERVAL_S - since)

                page = self._pending_page
                if page is None:
                    return

                # Record the current generation *before* capturing so we can
                # tell afterwards whether new requests came in.
                gen_before = self._generation

                await _emit_screenshot(page)
                self._last_emit = time.monotonic()

                # If no new requests arrived during the capture we're done.
                if self._generation == gen_before:
                    return
                # Otherwise loop to pick up the latest page reference.
        except Exception as exc:  # noqa: BLE001 - best-effort, never crash interactions
            url = getattr(self._pending_page, "url", "unknown") if self._pending_page else "no page"
            logger.warning(
                "Progressive screenshot failed (page=%s)", url,
                exc_info=True,
            )

    async def wait(self) -> None:
        """Await the in-flight capture task, if any.

        Called at the *end* of an interaction to guarantee the final frame
        is emitted before the tool returns.
        """
        if self._task is not None and not self._task.done():
            with contextlib.suppress(Exception):
                await self._task


_emitter = _ScreenshotEmitter()


def request_progressive_screenshot(page: Page) -> None:
    """Request a throttled, non-blocking progressive screenshot.

    This is the single entry-point that all interaction helpers (mouse movement,
    typing, scrolling) should call.

    Args:
        page: The Playwright page to capture.
    """
    _emitter.request(page)


async def flush_progressive_screenshot() -> None:
    """Ensure the in-flight progressive screenshot completes.

    Interaction functions should ``await`` this once at the very end (after
    the action finishes but before returning) so the final visual state is
    emitted without blocking the *middle* of the action.
    """
    await _emitter.wait()


# ---------------------------------------------------------------------------
# Post-tool screenshot decorator
# ---------------------------------------------------------------------------


def emit_screenshot_after[F: Callable[..., Any]](func: F) -> F:
    """Decorator that emits a browser screenshot after the wrapped tool runs.

    Wraps browser tool functions that return a page view string.
    After the tool completes, captures a screenshot via
    ``_emit_screenshot`` and publishes it to the UI.  The screenshot is NOT
    included in the tool's return value to avoid wasting context tokens.

    All settling (network idle, DOM quiet, CSS animations) is handled by
    ``wait_for_page_settle`` inside ``perform_interaction`` — this
    decorator only captures the screenshot.
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        result = await func(*args, **kwargs)

        # All decorated browser tools want a post-tool screenshot.
        # With string returns, just always emit.
        try:
            browser = await get_browser()
            page = await browser.current_page()
            await _emit_screenshot(page)
        except Exception as exc:  # noqa: BLE001 - never fail the tool call
            page_url = getattr(page, "url", "unknown") if page else "no page"
            closed = page.is_closed() if page and hasattr(page, "is_closed") else "?"
            logger.warning(
                "Post-tool screenshot failed (page=%s, closed=%s)",
                page_url, closed, exc_info=True,
            )

        return result

    return wrapper  # type: ignore


__all__ = [
    "emit_screenshot",
    "emit_screenshot_after",
    "flush_progressive_screenshot",
    "request_progressive_screenshot",
]
