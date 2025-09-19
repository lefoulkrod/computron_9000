"""Browser interaction tools (e.g. clicking elements).

Currently exposes:
        * ``click`` - Click an element by visible text or CSS selector and return a
            fresh ``PageSnapshot`` of the active page.

Design notes:
        * Re-uses the existing snapshot builder so semantics match ``open_url``.
        * Prefers exact visible text matches first; falls back to treating the
            target as a CSS selector when no text match is found.
        * Attempts to detect navigation triggered by the click (best-effort) and
            includes the navigation response when building the snapshot. If no
            navigation occurs within a short timeout, the snapshot is still built
            using the current page state (``response`` will be ``None``).
"""

from __future__ import annotations

import logging
from typing import Any, cast

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from tools.browser.core import get_browser
from tools.browser.core.snapshot import PageSnapshot, _build_page_snapshot
from tools.browser.exceptions import BrowserToolError

logger = logging.getLogger(__name__)


async def click(target: str) -> PageSnapshot:
    """Click an element by visible text or CSS selector and snapshot the page.

    The function attempts an exact visible text match first (``page.get_by_text``)
    because LLM callers most often refer to what they *see*. If no element with
    exactly that text exists, the ``target`` is treated as a CSS selector and
    queried via ``page.locator``. The first matching element is clicked.

    Args:
        target: Either a visible text string (e.g. "Book Now") or a CSS selector
            (e.g. "button#submit", "input[name='q']"). Leading/trailing
            whitespace is ignored for text matching.

    Returns:
        PageSnapshot: Structured snapshot of the page *after* the click.

    Raises:
        BrowserToolError: If no element is found, the page is blank, the click
            fails, or another browser error occurs.
    """
    clean_target = target.strip()
    if not clean_target:
        msg = "target must be a non-empty string"
        raise BrowserToolError(msg, tool="click")

    try:
        browser = await get_browser()
        page = await browser.current_page()
    except (PlaywrightError, RuntimeError) as exc:  # pragma: no cover - defensive wiring
        logger.exception("Unable to access browser page for click")
        msg = "Unable to access browser page"
        raise BrowserToolError(msg, tool="click") from exc

    if page.url in {"", "about:blank"}:
        msg = "Navigate to a page before attempting to click elements."
        raise BrowserToolError(msg, tool="click")

    # Locate element: try exact visible text first
    locator: Any | None = None
    try:
        text_locator = page.get_by_text(clean_target, exact=True)
        if await text_locator.count() > 0:  # pragma: no branch - simple branch
            locator = text_locator.first
    except PlaywrightError:  # pragma: no cover - text lookup unavailable
        locator = None

    if locator is None:
        # Fall back to treating it as a CSS selector
        try:
            css_locator = page.locator(clean_target).first
            if await css_locator.count() == 0:
                msg = f"No element found matching text or selector '{clean_target}'."
                raise BrowserToolError(msg, tool="click")
            locator = css_locator
        except BrowserToolError:
            raise  # re-raise explicit not found above
        except PlaywrightError as exc:  # pragma: no cover - unexpected selector failure
            logger.exception("Selector lookup failed for target %s", clean_target)
            msg = f"Failed to locate element for target '{clean_target}'."
            raise BrowserToolError(msg, tool="click") from exc

    # Attempt click & detect navigation (best-effort)
    response = None
    try:
        try:
            # Short timeout: many clicks won't navigate; we don't want to stall.
            async with page.expect_navigation(
                wait_until="domcontentloaded", timeout=3000
            ) as nav_ctx:
                await locator.click()
            # nav_ctx.value is an awaitable returning a Response
            response = cast("Any", await nav_ctx.value)  # Response | None
        except PlaywrightTimeoutError:
            # Click likely did not trigger navigation; perform direct click as fallback.
            await locator.click()
        except PlaywrightError as exc:
            logger.exception("Playwright error during click for target %s", clean_target)
            msg = f"Playwright error clicking element: {exc}"
            raise BrowserToolError(msg, tool="click") from exc

        # Build snapshot (response may be None if no navigation)
        return await _build_page_snapshot(page, response)
    except BrowserToolError:
        raise  # already wrapped
    except PlaywrightError as exc:  # pragma: no cover - final safety net
        logger.exception("Failed to build snapshot after click for target %s", clean_target)
        msg = "Failed to complete click operation"
        raise BrowserToolError(msg, tool="click") from exc


__all__ = ["click"]
