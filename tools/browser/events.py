"""Browser tool event emission helpers.

This module provides utilities to emit browser snapshot events after tool invocations,
allowing the UI to display live browser state during agent interactions.

Progressive snapshots (during mouse movement, typing, scrolling) are captured by a
background ``asyncio.Task`` on a throttled timer so that interaction loops are never
blocked by screenshot capture.  A single module-level ``_SnapshotEmitter`` manages
the lifecycle; callers simply invoke ``request_progressive_snapshot`` which returns
immediately.
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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Throttled background snapshot emitter
# ---------------------------------------------------------------------------

# Minimum interval between progressive screenshots (seconds).
# ~4 fps keeps the UI feeling live without saturating bandwidth.
_MIN_SNAPSHOT_INTERVAL_S: float = 0.25


class _SnapshotEmitter:
    """Fire-and-forget, throttled screenshot emitter.

    Interaction helpers call ``request`` to signal that a screenshot would be
    useful.  The emitter coalesces rapid requests and captures at most once per
    ``_MIN_SNAPSHOT_INTERVAL_S`` seconds, running the capture in a background
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
        # increments it; ``_run()`` records which generation it last captured
        # so it knows whether new requests arrived during a slow capture.
        self._generation: int = 0
        self._captured_generation: int = 0

    def request(self, page: Page) -> None:
        """Request a progressive snapshot.  Returns immediately.

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
                # Respect throttle - if we emitted very recently, wait out the
                # remainder of the interval so we don't flood the UI.
                since = time.monotonic() - self._last_emit
                if since < _MIN_SNAPSHOT_INTERVAL_S:
                    await asyncio.sleep(_MIN_SNAPSHOT_INTERVAL_S - since)

                page = self._pending_page
                if page is None:
                    return

                # Snapshot the current generation *before* capturing so we can
                # tell afterwards whether new requests came in.
                gen_before = self._generation

                await _emit_snapshot(page)
                self._last_emit = time.monotonic()
                self._captured_generation = gen_before

                # If no new requests arrived during the capture we're done.
                if self._generation == gen_before:
                    return
                # Otherwise loop to pick up the latest page reference.
        except Exception as exc:  # noqa: BLE001 - best-effort, never crash interactions
            logger.debug("Background snapshot emitter failed: %s", exc)

    async def wait(self) -> None:
        """Await the in-flight capture task, if any.

        Called at the *end* of an interaction to guarantee the final frame
        is emitted before the tool returns.
        """
        if self._task is not None and not self._task.done():
            with contextlib.suppress(Exception):
                await self._task


_emitter = _SnapshotEmitter()


def request_progressive_snapshot(page: Page) -> None:
    """Request a throttled, non-blocking progressive snapshot.

    This is the single entry-point that all interaction helpers (mouse movement,
    typing, scrolling) should call instead of the old blocking
    ``emit_snapshot_during_interaction``.

    Args:
        page: The Playwright page to capture.
    """
    _emitter.request(page)


async def flush_progressive_snapshot() -> None:
    """Ensure the in-flight progressive snapshot completes.

    Interaction functions should ``await`` this once at the very end (after
    the action finishes but before returning) so the final visual state is
    emitted without blocking the *middle* of the action.
    """
    await _emitter.wait()


async def _emit_snapshot(page: Page) -> None:
    """Capture a screenshot from *page* and publish it as a browser event.

    Uses JPEG at reduced quality for progressive frames (much smaller and
    faster to decode than PNG).
    """
    from agents.ollama.sdk.events import (
        AssistantResponse,
        BrowserSnapshotPayload,
        publish_event,
    )

    if not hasattr(page, "screenshot") or not callable(getattr(page, "screenshot", None)):
        return

    screenshot_bytes = await page.screenshot(type="jpeg", quality=55)
    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")

    url = getattr(page, "url", "")
    try:
        title = await page.title()
    except Exception:  # noqa: BLE001
        title = ""

    event_payload = BrowserSnapshotPayload(
        type="browser_snapshot",
        url=url,
        title=title,
        screenshot=screenshot_base64,
    )
    publish_event(AssistantResponse(event=event_payload))
    logger.debug("Emitted progressive snapshot for URL: %s", url)


def emit_browser_snapshot_on_page_change[F: Callable[..., Any]](func: F) -> F:
    """Decorator to emit browser snapshot events after page-changing interactions.

    Wraps browser tool functions that return InteractionResult or PageView.
    Captures a screenshot directly from the browser page and emits a browser_snapshot
    event for UI streaming. The screenshot is NOT included in the tool's return value
    to avoid wasting context tokens.

    Args:
        func: The browser tool function to wrap

    Returns:
        Wrapped function that emits events after execution
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        result = await func(*args, **kwargs)

        # Try to emit snapshot event if we have the necessary data
        try:
            from agents.ollama.sdk.events import (
                AssistantResponse,
                BrowserSnapshotPayload,
                publish_event,
            )
            from tools.browser.core import get_browser

            snapshot = None

            # Check if result has a page_view (InteractionResult)
            if hasattr(result, "page_view") and result.page_view is not None:
                snapshot = result.page_view
            # Check if result is a PageView directly
            elif hasattr(result, "url") and hasattr(result, "title"):
                snapshot = result

            # Emit event if we have snapshot data
            if snapshot:
                # Capture screenshot directly from the browser
                screenshot_base64 = None
                try:
                    browser = await get_browser()
                    page = await browser.current_page()

                    # Check if page has screenshot method (real browser, not test stub)
                    if not hasattr(page, "screenshot") or not callable(getattr(page, "screenshot", None)):
                        logger.debug("Page object doesn't have screenshot method, skipping snapshot event")
                        return result

                    # Shorter delay since we're already capturing during interactions
                    # Just need to ensure final page state is rendered
                    await page.wait_for_timeout(50)

                    screenshot_bytes = await page.screenshot(type="png")
                    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
                except Exception as screenshot_exc:  # noqa: BLE001 - best-effort screenshot
                    logger.debug("Failed to capture screenshot: %s", screenshot_exc)
                    return result  # Return early, don't emit event without screenshot

                # Only emit if we successfully captured a screenshot
                if screenshot_base64:
                    event_payload = BrowserSnapshotPayload(
                        type="browser_snapshot",
                        url=snapshot.url,
                        title=snapshot.title,
                        screenshot=screenshot_base64,
                    )
                    publish_event(AssistantResponse(event=event_payload))
                    logger.debug("Emitted browser snapshot event for URL: %s", snapshot.url)
        except Exception as exc:  # noqa: BLE001 - never fail the tool call
            # Don't fail the tool call if event emission fails
            logger.debug("Failed to emit browser snapshot event: %s", exc)

        return result

    return wrapper  # type: ignore


__all__ = [
    "emit_browser_snapshot_on_page_change",
    "flush_progressive_snapshot",
    "request_progressive_snapshot",
]
