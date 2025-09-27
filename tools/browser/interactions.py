"""Browser interaction tools.

This module exposes helpers for interacting with the active browser page. The
``click`` function clicks an element specified by visible text or a CSS selector
and returns a fresh ``PageSnapshot`` of the active page. The ``fill_field``
function enters text into an input or textarea located by the shared selector
resolution helper and also returns an updated ``PageSnapshot``.
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


async def fill_field(target: str, value: str | int | float | bool) -> PageSnapshot:
    """Type into a text-like input located by visible text or CSS selector.

    Args:
        target: Visible text or CSS selector identifying the input element.
        value: Textual value (converted to string) to type into the control.

    Returns:
        PageSnapshot: Snapshot of the page after the fill operation completes.

    Raises:
        BrowserToolError: If the element cannot be located, is unsupported, or
            Playwright raises an error while typing.
    """
    clean_target = target.strip()
    if not clean_target:
        msg = "target must be a non-empty string"
        raise BrowserToolError(msg, tool="fill_field")

    if value is None:
        msg = "value must not be None"
        raise BrowserToolError(msg, tool="fill_field")

    text_value = str(value)

    try:
        browser = await get_browser()
        page = await browser.current_page()
    except (PlaywrightError, RuntimeError) as exc:  # pragma: no cover - defensive wiring
        logger.exception("Unable to access browser page for fill_field")
        msg = "Unable to access browser page"
        raise BrowserToolError(msg, tool="fill_field") from exc

    if page.url in {"", "about:blank"}:
        msg = "Navigate to a page before attempting to fill elements."
        raise BrowserToolError(msg, tool="fill_field")

    try:
        resolution: _LocatorResolution | None = await _resolve_locator(
            page,
            clean_target,
            allow_substring_text=False,
            require_single_match=True,
            tool_name="fill_field",
        )
    except BrowserToolError:
        raise
    except PlaywrightError as exc:  # pragma: no cover - defensive
        logger.exception("Locator resolution failed for fill target %s", clean_target)
        msg = f"Failed to locate element for target '{clean_target}'."
        raise BrowserToolError(msg, tool="fill_field") from exc

    if resolution is None:
        msg = f"No element found matching text or selector '{clean_target}'."
        raise BrowserToolError(msg, tool="fill_field")

    locator = resolution.locator
    details = {
        "strategy": resolution.strategy,
        "query": resolution.query,
        "selector": resolution.resolved_selector,
    }

    tag_name = ""
    input_type = ""
    try:
        handle = await locator.element_handle()
        if handle is not None:
            tag_name = await handle.evaluate("el => el.tagName.toLowerCase()")
            if tag_name == "input":
                raw_type = await handle.get_attribute("type")
                input_type = (raw_type or "text").lower()
    except PlaywrightError as exc:  # pragma: no cover - defensive introspection aid
        logger.debug("Failed to introspect element for fill_field: %s", exc)

    if tag_name != "input" and tag_name != "textarea":
        msg = "fill_field only supports input and textarea elements"
        raise BrowserToolError(msg, tool="fill_field", details=details)

    unsupported_inputs = {"checkbox", "radio", "submit", "button", "image", "file", "hidden"}
    if tag_name == "input" and input_type in unsupported_inputs:
        msg = f"Input type '{input_type}' is not supported by fill_field."
        raise BrowserToolError(msg, tool="fill_field", details=details)

    try:
        await locator.click()
        await locator.fill("")
        await locator.type(text_value)
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Playwright error during fill_field for target %s", clean_target)
        msg = f"Playwright error filling element: {exc}"
        raise BrowserToolError(msg, tool="fill_field", details=details) from exc

    return await _build_page_snapshot(page, None)


__all__ = ["click", "fill_field"]
