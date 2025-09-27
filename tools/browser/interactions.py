"""Browser interaction tools.

This module exposes helpers for interacting with the active browser page. The
primary exported function is ``click`` which clicks an element specified by
visible text or a CSS selector and returns a fresh ``PageSnapshot`` of the
active page.

The function attempts to detect navigation triggered by the click and includes
the navigation response when building the snapshot; when no navigation occurs
within a short timeout the snapshot is still built from the current page state.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from tools.browser.core import get_browser
from tools.browser.core._selectors import _LocatorResolution, _resolve_locator
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.core.snapshot import PageSnapshot, _build_page_snapshot

logger = logging.getLogger(__name__)


async def click(target: str) -> PageSnapshot:
    """Click an element by visible text or CSS selector and snapshot the page.

    Args:
        target: Either a visible text string (e.g. ``"Book Now"``) or a CSS
            selector (e.g. ``"button#submit"``, ``"input[name='q']"``). Leading
            and trailing whitespace is ignored for text matching.

    Returns:
        PageSnapshot: Structured snapshot of the page after performing the click.

    Raises:
        BrowserToolError: If the target is empty, no element is found, the page is
            blank, the click fails, or another browser error occurs.
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

    try:
        resolution: _LocatorResolution | None = await _resolve_locator(
            page,
            clean_target,
            allow_substring_text=False,
            require_single_match=True,
            tool_name="click",
        )
    except BrowserToolError:
        raise
    except PlaywrightError as exc:  # pragma: no cover - defensive
        logger.exception("Locator resolution failed for target %s", clean_target)
        msg = f"Failed to locate element for target '{clean_target}'."
        raise BrowserToolError(msg, tool="click") from exc

    if resolution is None:
        msg = f"No element found matching text or selector '{clean_target}'."
        raise BrowserToolError(msg, tool="click")

    locator = resolution.locator
    details = {
        "strategy": resolution.strategy,
        "query": resolution.query,
        "selector": resolution.resolved_selector,
    }

    # Attempt click & detect navigation (best-effort)
    response = None
    try:
        try:
            # Short timeout: many clicks won't navigate; we don't want to stall.
            async with page.expect_navigation(wait_until="domcontentloaded", timeout=3000) as nav_ctx:
                await locator.click()
            # nav_ctx.value is an awaitable returning a Response
            response = cast("Any", await nav_ctx.value)  # Response | None
        except PlaywrightTimeoutError:
            # Click likely did not trigger navigation; perform direct click as fallback.
            await locator.click()
        except PlaywrightError as exc:
            logger.exception("Playwright error during click for target %s", clean_target)
            msg = f"Playwright error clicking element: {exc}"
            raise BrowserToolError(msg, tool="click", details=details) from exc

        # Build snapshot (response may be None if no navigation)
        return await _build_page_snapshot(page, response)
    except BrowserToolError:
        raise  # already wrapped
    except PlaywrightError as exc:  # pragma: no cover - final safety net
        logger.exception("Failed to build snapshot after click for target %s", clean_target)
        msg = "Failed to complete click operation"
        raise BrowserToolError(msg, tool="click", details=details) from exc


__all__ = ["click"]
