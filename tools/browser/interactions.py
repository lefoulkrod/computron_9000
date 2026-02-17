"""Browser interaction tools.

This module exposes helpers for interacting with the active browser page. The
``click`` function clicks an element specified by visible text or a selector and
Each tool returns an ``InteractionResult`` with a ``page_view``
showing the updated page content and interactive elements.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any, Literal

from playwright.async_api import Error as PlaywrightError
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from playwright.async_api import Page, Response

from tools.browser.core import get_browser
from tools.browser.core._selectors import _LocatorResolution, _resolve_locator
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.core.human import (
    human_click,
    human_drag,
    human_press_keys,
    human_scroll,
    human_type,
)
from tools.browser.core.page_view import PageView, build_page_view
from tools.browser.events import emit_browser_snapshot_on_page_change

Reason = Literal["browser-navigation", "history-navigation", "dom-mutation", "no-change", "scroll"]


class InteractionResult(BaseModel):
    """Public result returned by interaction tools.

    Attributes:
        page_view: Page view with ``[role] name`` markers for interactive
            elements.  The agent can pull selectors directly from the content
            (e.g. ``button:Add to Cart``) for use in ``click()``,
            ``fill_field()``, etc.
        page_changed: True if navigation or DOM mutation was detected.
        reason: Classification of the change (browser-navigation, dom-mutation, no-change, etc.).
        extras: Additional tool-specific metadata (scroll position, etc.).
    """

    page_view: PageView | None = None
    page_changed: bool
    reason: Reason
    extras: dict[str, Any] = Field(default_factory=dict)


logger = logging.getLogger(__name__)


async def _build_snapshot(
    page: Page,
    response: Response | None,
) -> PageView:
    """Build page view for interaction results."""
    return await build_page_view(page, response)


@emit_browser_snapshot_on_page_change
async def click(selector: str) -> InteractionResult:
    """Click an element and return change metadata with an updated page snapshot.

    Click can only be performed on elements that are visible on the page.
    Always returns a snapshot so you can detect AJAX changes (e.g., cart updates)
    by comparing snippet content before and after the click.

    Args:
        selector: Element selector in ``role:name`` format from snapshot output.
            Example: ``click("button:Add to Cart")`` or ``click("link:Sign In")``.

    Returns:
        InteractionResult: Contains snapshot (always), page_changed (bool), and reason.
            For AJAX actions (e.g., add-to-cart on search results), page_changed may be
            False but snapshot content changes. Compare before/after to detect updates.

    Raises:
        BrowserToolError: If the target is empty, no element is found, the page is
            blank, the click fails, or another browser error occurs.
    """
    clean_selector = selector.strip()
    if not clean_selector:
        msg = "selector must be a non-empty string"
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
            clean_selector,
            allow_substring_text=False,
            require_single_match=True,
            tool_name="click",
        )
    except BrowserToolError:
        raise
    except PlaywrightError as exc:  # pragma: no cover - defensive
        logger.exception("Locator resolution failed for selector %s", clean_selector)
        msg = f"Failed to locate element for selector '{clean_selector}'."
        raise BrowserToolError(msg, tool="click") from exc

    if resolution is None:
        msg = f"No element found matching text or selector '{clean_selector}'."
        raise BrowserToolError(msg, tool="click")

    locator = resolution.locator
    details = {
        "strategy": resolution.strategy,
        "query": resolution.query,
        "selector": resolution.resolved_selector,
    }

    try:

        async def _perform_click() -> None:
            await human_click(page, locator)

        browser_result = await browser.perform_interaction(page, _perform_click)
        # Always capture a snapshot so AJAX interactions (e.g., add-to-cart on search
        # results) provide visible feedback to the agent via changed snippet content
        annotated = await _build_snapshot(page, browser_result.navigation_response)
        return InteractionResult(
            page_view=annotated,
            page_changed=browser_result.page_changed,
            reason=browser_result.reason,
        )
    except BrowserToolError:
        raise  # already wrapped
    except PlaywrightError as exc:  # pragma: no cover - final safety net
        logger.exception("Failed to build snapshot after click for selector %s", clean_selector)
        msg = "Failed to complete click operation"
        raise BrowserToolError(msg, tool="click", details=details) from exc


@emit_browser_snapshot_on_page_change
async def drag(
    source: str,
    *,
    target: str | None = None,
    offset: tuple[float | int, float | int] | None = None,
) -> InteractionResult:
    """Drag from a source element to a target or offset and return change metadata.

    Args:
        source: Visible text on the element or a selector handle returned by page
            snapshots and other tools. The provided text or selector must uniquely
            identify the drag start element.
        target: Optional visible text or selector handle identifying the drop destination
            element. When supplied, the text or selector must uniquely identify a single
            element on the page.
        offset: Optional ``(dx, dy)`` tuple specifying a pixel offset relative to the
            source element's center. Provide either ``target`` or ``offset`` (not both).

    Returns:
        InteractionResult: Change metadata plus a snapshot when the page changed.

    Raises:
        BrowserToolError: If the page is blank, locators cannot be resolved, inputs are
            invalid, or the drag fails.
    """
    clean_source = source.strip()
    if not clean_source:
        raise BrowserToolError("source must be a non-empty string", tool="drag")

    has_target = target is not None
    has_offset = offset is not None
    if (not has_target and not has_offset) or (has_target and has_offset):
        raise BrowserToolError("Provide either target selector or offset", tool="drag")

    offset_tuple: tuple[float, float] | None = None
    if offset is not None:
        if isinstance(offset, tuple | list) and len(offset) == 2:
            try:
                offset_tuple = (float(offset[0]), float(offset[1]))
            except (TypeError, ValueError) as exc:
                raise BrowserToolError("offset must contain numeric values", tool="drag") from exc
            if not all(math.isfinite(component) for component in offset_tuple):
                raise BrowserToolError("offset values must be finite numbers", tool="drag")
        else:
            raise BrowserToolError("offset must be a length-2 tuple of numbers", tool="drag")

    clean_target: str | None = None
    if target is not None:
        clean_target = target.strip()
        if not clean_target:
            raise BrowserToolError("target selector must be a non-empty string", tool="drag")

    try:
        browser = await get_browser()
        page = await browser.current_page()
    except (PlaywrightError, RuntimeError) as exc:  # pragma: no cover - defensive wiring
        logger.exception("Unable to access browser page for drag")
        msg = "Unable to access browser page"
        raise BrowserToolError(msg, tool="drag") from exc

    if page.url in {"", "about:blank"}:
        raise BrowserToolError("Navigate to a page before attempting to drag.", tool="drag")

    try:
        source_resolution: _LocatorResolution | None = await _resolve_locator(
            page,
            clean_source,
            allow_substring_text=False,
            require_single_match=True,
            tool_name="drag",
        )
    except BrowserToolError:
        raise
    except PlaywrightError as exc:  # pragma: no cover - defensive
        logger.exception("Locator resolution failed for drag source %s", clean_source)
        msg = f"Failed to locate element for source '{clean_source}'."
        raise BrowserToolError(msg, tool="drag") from exc

    if source_resolution is None:
        msg = f"No element found matching text or selector '{clean_source}'."
        raise BrowserToolError(msg, tool="drag")

    target_resolution: _LocatorResolution | None = None
    if clean_target is not None:
        try:
            target_resolution = await _resolve_locator(
                page,
                clean_target,
                allow_substring_text=False,
                require_single_match=True,
                tool_name="drag",
            )
        except BrowserToolError:
            raise
        except PlaywrightError as exc:  # pragma: no cover - defensive
            logger.exception("Locator resolution failed for drag target %s", clean_target)
            msg = f"Failed to locate element for target '{clean_target}'."
            raise BrowserToolError(msg, tool="drag") from exc

        if target_resolution is None:
            msg = f"No element found matching text or selector '{clean_target}'."
            raise BrowserToolError(msg, tool="drag")

    details: dict[str, Any] = {
        "source": {
            "strategy": source_resolution.strategy,
            "selector": source_resolution.resolved_selector,
            "query": source_resolution.query,
        }
    }
    if target_resolution is not None:
        details["target"] = {
            "strategy": target_resolution.strategy,
            "selector": target_resolution.resolved_selector,
            "query": target_resolution.query,
        }
    if offset_tuple is not None:
        details["offset"] = offset_tuple

    async def _perform_drag() -> None:
        await human_drag(
            page,
            source_resolution.locator,
            target_locator=target_resolution.locator if target_resolution else None,
            offset=offset_tuple,
        )

    try:
        browser_result = await browser.perform_interaction(page, _perform_drag)
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Playwright error during drag for source %s", clean_source)
        msg = "Playwright error performing drag"
        raise BrowserToolError(msg, tool="drag", details=details) from exc

    annotated = None
    if browser_result.page_changed:
        annotated = await _build_snapshot(page, browser_result.navigation_response)
    return InteractionResult(
        page_view=annotated,
        page_changed=browser_result.page_changed,
        reason=browser_result.reason,
    )


@emit_browser_snapshot_on_page_change
async def fill_field(selector: str, value: str | int | float | bool | None) -> InteractionResult:
    """Type into a text-like input and return change metadata with optional snapshot.

    Types the complete text value character-by-character with human-like delays (45-140ms
    per character, with periodic pauses). Always pass the full string in a single call
    for natural typing rhythm—do not call multiple times with individual characters.

    Args:
        selector: Element selector in ``role:name`` format from snapshot output.
            Example: ``fill_field("textbox:Email", "user@example.com")``.
        value: Textual value (converted to string) to type into the control.
            Pass complete strings: "laptop computers", not individual characters.

    Returns:
        InteractionResult: Change metadata plus a snapshot when the page changed.

    Raises:
        BrowserToolError: If the element cannot be located, is unsupported, or
            Playwright raises an error while typing.
    """
    clean_selector = selector.strip()
    if not clean_selector:
        msg = "selector must be a non-empty string"
        raise BrowserToolError(msg, tool="fill_field")

    # Allow callers to pass None; convert to empty string for typing into fields.
    # This keeps the runtime behavior flexible while still typing the parameter.
    text_value = "" if value is None else str(value)

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
            clean_selector,
            allow_substring_text=False,
            require_single_match=True,
            tool_name="fill_field",
        )
    except BrowserToolError:
        raise
    except PlaywrightError as exc:  # pragma: no cover - defensive
        logger.exception("Locator resolution failed for fill selector %s", clean_selector)
        msg = f"Failed to locate element for selector '{clean_selector}'."
        raise BrowserToolError(msg, tool="fill_field") from exc

    if resolution is None:
        msg = f"No element found matching text or selector '{clean_selector}'."
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
        handle = await locator.element_handle(timeout=5000)
        if handle is not None:
            tag_name = await handle.evaluate("el => el.tagName.toLowerCase()")
            if tag_name == "input":
                raw_type = await handle.get_attribute("type")
                input_type = (raw_type or "text").lower()
    except PlaywrightError as exc:  # pragma: no cover - defensive introspection aid
        logger.debug("Failed to introspect element for fill_field: %s", exc)

    if tag_name not in {"input", "textarea"}:
        msg = "fill_field only supports input and textarea elements"
        raise BrowserToolError(msg, tool="fill_field", details=details)

    unsupported_inputs = {"checkbox", "radio", "submit", "button", "image", "file", "hidden"}
    if tag_name == "input" and input_type in unsupported_inputs:
        msg = f"Input type '{input_type}' is not supported by fill_field."
        raise BrowserToolError(msg, tool="fill_field", details=details)

    async def _perform_fill() -> None:
        # Try human-like click first, fall back to force click if needed
        try:
            await human_click(page, locator)
        except PlaywrightError:
            # If human_click fails (e.g., element obscured), use force click
            await locator.click(force=True, timeout=5000)
        await human_type(page, locator, text_value, clear_existing=True)

    try:
        browser_result = await browser.perform_interaction(page, _perform_fill)
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Playwright error during fill_field for selector %s", clean_selector)
        msg = f"Playwright error filling element: {exc}"
        raise BrowserToolError(msg, tool="fill_field", details=details) from exc

    annotated = None
    if browser_result.page_changed:
        annotated = await _build_snapshot(page, browser_result.navigation_response)
    return InteractionResult(
        page_view=annotated,
        page_changed=browser_result.page_changed,
        reason=browser_result.reason,
    )


@emit_browser_snapshot_on_page_change
async def press_keys(keys: list[str]) -> InteractionResult:
    """Press keyboard keys and return change metadata with optional snapshot.

    Args:
        keys: Ordered list of key names (for example: "Enter", "Escape", "ArrowDown",
            or modifier chords such as "Control+Shift+P"). Keys are applied to the
            currently focused element on the active page.

    Returns:
        InteractionResult: Change metadata plus a snapshot when the page changed.

    Raises:
        BrowserToolError: If keys are invalid, the page is not navigated, or key presses fail.
    """
    if not isinstance(keys, list) or len(keys) == 0:
        raise BrowserToolError("keys must be a non-empty list of key names", tool="press_keys")

    try:
        browser = await get_browser()
        page = await browser.current_page()
    except (PlaywrightError, RuntimeError) as exc:  # pragma: no cover - defensive wiring
        logger.exception("Unable to access browser page for press_keys")
        msg = "Unable to access browser page"
        raise BrowserToolError(msg, tool="press_keys") from exc

    if page.url in {"", "about:blank"}:
        msg = "Navigate to a page before attempting to press keys."
        raise BrowserToolError(msg, tool="press_keys")

    async def _perform_press() -> None:
        await human_press_keys(page, keys)

    try:
        browser_result = await browser.perform_interaction(page, _perform_press)
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Playwright error during press_keys for keys %s", keys)
        msg = f"Playwright error pressing keys: {exc}"
        raise BrowserToolError(msg, tool="press_keys") from exc

    annotated = None
    if browser_result.page_changed:
        annotated = await _build_snapshot(page, browser_result.navigation_response)
    return InteractionResult(
        page_view=annotated,
        page_changed=browser_result.page_changed,
        reason=browser_result.reason,
    )


@emit_browser_snapshot_on_page_change
async def scroll_page(direction: str = "down", amount: int | None = None) -> InteractionResult:
    """Scroll the page and return change metadata, scroll telemetry, and snapshot.

    The returned snapshot contains viewport-visible structured text (up to 2000 chars)
    that changes based on the current scroll position, allowing the agent to read
    different parts of the page as it scrolls.

    Args:
        direction: One of {"down", "up", "page_down", "page_up", "top", "bottom"}.
        amount: Optional pixel distance for fine-grained scrolling when direction
            is "down" or "up". If omitted, a viewport-sized scroll is performed.

    Returns:
        InteractionResult: Always returns page_changed=True with a minimal snapshot
        (title, url, snippet, status_code) and scroll state in extras.

    Raises:
        BrowserToolError: If direction is invalid or the page is not navigated.
    """
    if not isinstance(direction, str) or not direction:
        raise BrowserToolError("direction must be a non-empty string", tool="scroll_page")

    try:
        browser = await get_browser()
        page = await browser.current_page()
    except (PlaywrightError, RuntimeError) as exc:  # pragma: no cover - defensive wiring
        logger.exception("Unable to access browser page for scroll_page")
        raise BrowserToolError("Unable to access browser page", tool="scroll_page") from exc

    if page.url in {"", "about:blank"}:
        raise BrowserToolError("Navigate to a page before attempting to scroll.", tool="scroll_page")

    async def _perform_scroll() -> None:
        await human_scroll(page, direction=direction, amount=amount)

    try:
        await browser.perform_interaction(page, _perform_scroll)
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Playwright error during scroll_page for direction %s", direction)
        raise BrowserToolError(f"Playwright error performing scroll: {exc}", tool="scroll_page") from exc

    # Build snapshot which includes viewport/scroll info
    annotated = await _build_snapshot(page, None)  # Scroll never produces navigation

    return InteractionResult(
        page_view=annotated,
        page_changed=True,
        reason="scroll",
        extras={"scroll": annotated.viewport},  # Expose viewport data in extras for convenience
    )


@emit_browser_snapshot_on_page_change
async def go_back() -> InteractionResult:
    """Navigate back in history and return change metadata with an updated snapshot.

    Returns:
        InteractionResult: Change metadata plus a snapshot when navigation succeeds.

    Raises:
        BrowserToolError: If the browser page cannot be accessed or back navigation fails.
    """
    try:
        browser = await get_browser()
        page = await browser.current_page()
    except (PlaywrightError, RuntimeError) as exc:  # pragma: no cover - defensive wiring
        logger.exception("Unable to access browser page for go_back")
        msg = "Unable to access browser page"
        raise BrowserToolError(msg, tool="go_back") from exc

    if page.url in {"", "about:blank"}:
        msg = "No navigated page available for back navigation."
        raise BrowserToolError(msg, tool="go_back")

    async def _perform_back() -> None:
        await page.go_back(wait_until="domcontentloaded")

    try:
        browser_result = await browser.perform_interaction(page, _perform_back)
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Playwright error during go_back")
        msg = "Failed to navigate back"
        raise BrowserToolError(msg, tool="go_back") from exc

    if not browser_result.page_changed:
        msg = "No previous page available to navigate back to."
        raise BrowserToolError(msg, tool="go_back")

    annotated = await _build_snapshot(page, browser_result.navigation_response)
    return InteractionResult(
        page_view=annotated,
        page_changed=browser_result.page_changed,
        reason=browser_result.reason,
    )


__all__ = [
    "InteractionResult",
    "click",
    "drag",
    "fill_field",
    "go_back",
    "press_keys",
    "scroll_page",
]
