"""Browser interaction tools.

This module exposes helpers for interacting with the active browser page.
Each tool returns a formatted page view string showing the updated page
content and interactive elements.
"""

from __future__ import annotations

import contextvars
import logging
import math
from typing import TYPE_CHECKING, Any

from playwright.async_api import Error as PlaywrightError

if TYPE_CHECKING:
    from playwright.async_api import Response

from config import load_config
from tools.browser.core import get_active_view, get_browser
from tools.browser.core._formatting import format_page_view
from tools.browser.core._selectors import _LocatorResolution, _resolve_locator
from tools.browser.core.browser import BrowserInteractionResult
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.core.human import (
    human_click,
    human_click_at,
    human_drag,
    human_press_and_hold,
    human_press_and_hold_at,
    human_press_keys,
    human_scroll,
    human_type,
)
from tools.browser.core.page_view import PageView, build_page_view
from tools.browser.events import emit_screenshot_after

# ---------------------------------------------------------------------------
# Scroll budget tracking
# ---------------------------------------------------------------------------
# Tracks scroll calls per page URL to prevent the agent from scrolling
# endlessly. Resets when the URL changes (navigation, click-through, etc.).
# Uses contextvars so each async task (request/agent invocation) gets its own
# independent scroll budget — no cross-request interference.
_scroll_count_var: contextvars.ContextVar[int] = contextvars.ContextVar("_scroll_count", default=0)
_scroll_url_var: contextvars.ContextVar[str] = contextvars.ContextVar("_scroll_url", default="")


logger = logging.getLogger(__name__)


def _log_browser_panel(
    result: BrowserInteractionResult,
    *,
    snapshot: PageView | None,
    tool_name: str = "",
    resolution: _LocatorResolution | None = None,
) -> None:
    """Emit a single Rich panel summarising a browser tool call."""
    if not logger.isEnabledFor(logging.DEBUG):
        return

    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    table = Table(show_header=False, expand=False, padding=(0, 1))
    table.add_column("Phase", style="bold")
    table.add_column("Duration", justify="right")
    table.add_column("Status")

    if result.action_ms > 0:
        table.add_row("interaction", f"{result.action_ms:.0f}ms", "")

    settle = result.settle_timings
    if settle is not None:
        for name, duration_ms, timed_out in settle.phases:
            status = "[yellow]timeout[/yellow]" if timed_out else "[green]ok[/green]"
            table.add_row(name, f"{duration_ms:.0f}ms", status)
        if settle.error:
            table.add_row("error", "", f"[red]{settle.error}[/red]")

    if snapshot is not None and snapshot.snapshot_nodes > 0:
        total_snap = snapshot.snapshot_js_ms + snapshot.snapshot_py_ms
        table.add_row("snapshot", f"{total_snap:.0f}ms", f"{snapshot.snapshot_nodes} nodes")

    settle_total = settle.total_ms if settle else 0
    snap_total = (snapshot.snapshot_js_ms + snapshot.snapshot_py_ms) if snapshot else 0
    total_ms = result.action_ms + settle_total + snap_total

    url = snapshot.url if snapshot else ""
    display_url = url if len(url) <= 80 else url[:77] + "…"

    # Title: "click  ref=7 → [data-ct-ref='7']" or just "browser"
    title_parts: list[str] = [f"[bold cyan]{tool_name or 'browser'}[/bold cyan]"]
    if resolution:
        title_parts.append(f"ref={resolution.query}")
    title = "  ".join(title_parts)

    # Subtitle: total + url + optional frame/download info
    parts: list[str] = [f"total=[bold]{total_ms:.0f}ms[/bold]"]
    if display_url:
        parts.append(display_url)
    if result.frame_transition:
        parts.append(f"frame: {result.frame_transition}")
    if result.download:
        parts.append(f"download: {result.download.filename}")
    subtitle = "  ".join(parts)

    console = Console(stderr=True)
    console.print(Panel(
        table,
        title=title,
        subtitle=subtitle,
        border_style="dim",
        expand=False,
    ))


async def _build_snapshot(
    response: Response | None,
) -> PageView:
    """Build page view for interaction results using the active view."""
    browser = await get_browser()
    view = await browser.active_view()
    return await build_page_view(view, response)


async def _format_result(
    result: BrowserInteractionResult,
    *,
    tool_name: str = "",
    resolution: _LocatorResolution | None = None,
) -> str:
    """Format a BrowserInteractionResult as a page view string."""
    if result.download is not None:
        _log_browser_panel(result, snapshot=None, tool_name=tool_name, resolution=resolution)
        return format_page_view(
            title="File Download",
            url="",
            status_code=200,
            content="",
            viewport=None,
            truncated=False,
            downloaded_file=result.download,
        )
    snapshot = await _build_snapshot(result.navigation_response)
    _log_browser_panel(result, snapshot=snapshot, tool_name=tool_name, resolution=resolution)
    return format_page_view(
        title=snapshot.title,
        url=snapshot.url,
        status_code=snapshot.status_code,
        viewport=snapshot.viewport,
        content=snapshot.content,
        truncated=snapshot.truncated,
    )


def _validate_bbox(
    x1: float | int, y1: float | int, x2: float | int, y2: float | int,
    *, tool_name: str,
) -> tuple[float, float, float, float]:
    """Validate and convert bounding box coordinates."""
    try:
        coords = (float(x1), float(y1), float(x2), float(y2))
    except (TypeError, ValueError) as exc:
        raise BrowserToolError("All coordinates must be numeric", tool=tool_name) from exc
    if not all(math.isfinite(c) for c in coords):
        raise BrowserToolError("All coordinates must be finite numbers", tool=tool_name)
    return coords


async def _resolve_or_raise(
    frame: Any,
    selector: str,
    *,
    tool_name: str,
) -> _LocatorResolution:
    """Resolve a ref number or selector, raising BrowserToolError on failure."""
    try:
        resolution = await _resolve_locator(
            frame,
            selector,
            tool_name=tool_name,
        )
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Locator resolution failed for %s selector %s", tool_name, selector)
        msg = f"Failed to locate element for selector '{selector}'."
        raise BrowserToolError(msg, tool=tool_name) from exc
    if resolution is None:
        msg = f"No element found for '{selector}'. Use a ref number from browse_page() output."
        raise BrowserToolError(msg, tool=tool_name)
    return resolution


@emit_screenshot_after
async def click(selector: str) -> str:
    """Click an element by its ref number from the page view.

    Always returns an updated page snapshot.  For AJAX actions (e.g. add-to-cart),
    ``page_changed`` may be False but snapshot content will differ.

    Args:
        selector: Ref number from ``browse_page()`` output.
            Examples: ``"7"``, ``"12"``.

    Returns:
        Updated page snapshot string.

    Raises:
        BrowserToolError: If the element is not found or the click fails.
    """
    clean_selector = selector.strip()
    if not clean_selector:
        msg = "selector must be a non-empty string"
        raise BrowserToolError(msg, tool="click")

    browser, view = await get_active_view("click")

    try:
        resolution = await _resolve_or_raise(view.frame, clean_selector, tool_name="click")
    except BrowserToolError as exc:
        return str(exc)

    try:
        result = await browser.perform_interaction(lambda: human_click(view.frame, resolution.locator))
        return await _format_result(result, tool_name="click", resolution=resolution)
    except BrowserToolError as exc:
        return str(exc)
    except PlaywrightError as exc:  # pragma: no cover - final safety net
        logger.exception("Failed to build snapshot after click for selector %s", clean_selector)
        return "[click] Failed to complete click operation."


@emit_screenshot_after
async def press_and_hold(selector: str, duration_ms: int = 3000) -> str:
    """Press and hold an element for a specified duration.

    Use this for bot-detection challenges that require holding a button down
    for several seconds (e.g. Walmart's press-and-hold verification).

    Args:
        selector: Ref number from ``browse_page()`` output.
            Examples: ``"7"``, ``"12"``.
        duration_ms: How long to hold the mouse button in milliseconds.
            Defaults to 3000 (3 seconds). Range: 500-10000.

    Returns:
        Updated page snapshot string after the hold is released.

    Raises:
        BrowserToolError: If the element is not found or the hold fails.
    """
    clean_selector = selector.strip()
    if not clean_selector:
        raise BrowserToolError("selector must be a non-empty string", tool="press_and_hold")

    clamped_duration = max(500, min(10000, duration_ms))

    browser, view = await get_active_view("press_and_hold")

    resolution = await _resolve_or_raise(view.frame, clean_selector, tool_name="press_and_hold")

    details = {
        "query": resolution.query,
        "selector": resolution.resolved_selector,
        "duration_ms": clamped_duration,
    }

    try:
        result = await browser.perform_interaction(
            lambda: human_press_and_hold(view.frame, resolution.locator, duration_ms=clamped_duration),
        )
        return await _format_result(result, tool_name="press_and_hold", resolution=resolution)
    except BrowserToolError:
        raise
    except PlaywrightError as exc:  # pragma: no cover - final safety net
        logger.exception("Failed to complete press_and_hold for selector %s", clean_selector)
        raise BrowserToolError(
            "Failed to complete press_and_hold operation",
            tool="press_and_hold",
            details=details,
        ) from exc


@emit_screenshot_after
async def drag(
    source: str,
    *,
    target: str | None = None,
    offset: tuple[float | int, float | int] | None = None,
) -> str:
    """Drag from a source element to a target element or by pixel offset.

    Provide either ``target`` or ``offset``, not both.

    Args:
        source: Ref number from ``browse_page()`` for the drag start element.
        target: Optional ref number for the drop destination.
        offset: Optional ``(dx, dy)`` pixel offset from source center.

    Returns:
        Updated page snapshot string.

    Raises:
        BrowserToolError: If elements are not found or the drag fails.
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

    browser, view = await get_active_view("drag")

    source_resolution = await _resolve_or_raise(view.frame, clean_source, tool_name="drag")

    target_resolution: _LocatorResolution | None = None
    if clean_target is not None:
        target_resolution = await _resolve_or_raise(view.frame, clean_target, tool_name="drag")

    details: dict[str, Any] = {
        "source": {
            "selector": source_resolution.resolved_selector,
            "query": source_resolution.query,
        }
    }
    if target_resolution is not None:
        details["target"] = {
            "selector": target_resolution.resolved_selector,
            "query": target_resolution.query,
        }
    if offset_tuple is not None:
        details["offset"] = offset_tuple

    async def _perform_drag() -> None:
        await human_drag(
            view.frame,
            source_resolution.locator,
            target_locator=target_resolution.locator if target_resolution else None,
            offset=offset_tuple,
        )

    try:
        browser_result = await browser.perform_interaction(_perform_drag)
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Playwright error during drag for source %s", clean_source)
        msg = "Playwright error performing drag"
        raise BrowserToolError(msg, tool="drag", details=details) from exc

    return await _format_result(browser_result, tool_name="drag", resolution=source_resolution)


@emit_screenshot_after
async def fill_field(selector: str, value: str | int | float | bool | None) -> str:
    """Type into a text input or textarea field.

    Pass the complete text in a single call — do not call multiple times
    with individual characters.  Returns an updated page snapshot.

    Args:
        selector: Ref number from ``browse_page()`` output.
            Examples: ``"7"``, ``"12"``.
        value: The complete text to type (converted to string).

    Returns:
        Updated page snapshot string.

    Raises:
        BrowserToolError: If the element is not found or is unsupported.
    """
    clean_selector = selector.strip()
    if not clean_selector:
        msg = "selector must be a non-empty string"
        raise BrowserToolError(msg, tool="fill_field")

    # Allow callers to pass None; convert to empty string for typing into fields.
    text_value = "" if value is None else str(value)

    browser, view = await get_active_view("fill_field")

    resolution = await _resolve_or_raise(view.frame, clean_selector, tool_name="fill_field")

    locator = resolution.locator
    details = {
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
        try:
            await human_click(view.frame, locator)
        except PlaywrightError:
            await locator.click(force=True, timeout=5000)
        await human_type(view.frame, locator, text_value, clear_existing=True)

    try:
        result = await browser.perform_interaction(_perform_fill)
        return await _format_result(result, tool_name="fill_field", resolution=resolution)
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Playwright error during fill_field for selector %s", clean_selector)
        msg = f"Playwright error filling element: {exc}"
        raise BrowserToolError(msg, tool="fill_field", details=details) from exc


@emit_screenshot_after
async def press_keys(keys: list[str]) -> str:
    """Press keyboard keys on the currently focused element.

    Commonly used after ``fill_field()`` to submit a form
    (``press_keys(["Enter"])``), or to dismiss dialogs (``["Escape"]``).

    Args:
        keys: List of key names.  Examples: ``["Enter"]``, ``["Escape"]``,
            ``["ArrowDown"]``, ``["Control+Shift+P"]``.

    Returns:
        Updated page snapshot string.

    Raises:
        BrowserToolError: If keys are invalid or key presses fail.
    """
    if not isinstance(keys, list) or len(keys) == 0:
        raise BrowserToolError("keys must be a non-empty list of key names", tool="press_keys")

    browser, view = await get_active_view("press_keys")

    try:
        result = await browser.perform_interaction(lambda: human_press_keys(view.frame, keys))
        return await _format_result(result, tool_name="press_keys")
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Playwright error during press_keys for keys %s", keys)
        msg = f"Playwright error pressing keys: {exc}"
        raise BrowserToolError(msg, tool="press_keys") from exc


@emit_screenshot_after
async def scroll_page(direction: str = "down", amount: int | None = None) -> str:
    """Scroll the page and return an updated snapshot.

    A scroll budget is enforced per URL.  After several scrolls a warning
    appears; after the hard limit, scrolling is refused.  Use
    ``browse_page(full_page=True)`` or ``save_page_content()`` instead of
    excessive scrolling.

    Args:
        direction: ``"down"``, ``"up"``, ``"page_down"``, ``"page_up"``,
            ``"top"``, or ``"bottom"``.
        amount: Optional pixel distance for ``"down"``/``"up"``.  Omit for
            a viewport-sized scroll.

    Returns:
        Updated page snapshot string with scroll state.

    Raises:
        BrowserToolError: If direction is invalid or scroll budget exhausted.
    """
    if not isinstance(direction, str) or not direction:
        raise BrowserToolError("direction must be a non-empty string", tool="scroll_page")

    browser, view = await get_active_view("scroll_page")

    cfg = load_config()
    warn_threshold = cfg.tools.browser.scroll_warn_threshold
    hard_limit = cfg.tools.browser.scroll_hard_limit

    scroll_count = _scroll_count_var.get()
    scroll_url = _scroll_url_var.get()

    # Reset counter when the page URL changes (navigation, click-through, etc.)
    if view.url != scroll_url:
        _scroll_url_var.set(view.url)
        scroll_count = 0

    # Hard limit: refuse to scroll further
    if scroll_count >= hard_limit:
        raise BrowserToolError(
            f"Scroll limit reached ({hard_limit} scrolls on this page). "
            "STOP scrolling. Use browse_page(full_page=True) to read the entire page, "
            "or save_page_content(filename) to save it as markdown for processing.",
            tool="scroll_page",
        )

    scroll_count += 1
    _scroll_count_var.set(scroll_count)

    try:
        interaction_result = await browser.perform_interaction(lambda: human_scroll(view.frame, direction=direction, amount=amount))
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Playwright error during scroll_page for direction %s", direction)
        raise BrowserToolError(f"Playwright error performing scroll: {exc}", tool="scroll_page") from exc

    # Build snapshot which includes viewport/scroll info
    annotated = await _build_snapshot(None)  # Scroll never produces navigation
    _log_browser_panel(interaction_result, snapshot=annotated, tool_name="scroll_page")

    content = annotated.content
    # Inject warning after threshold
    if scroll_count >= warn_threshold:
        remaining = hard_limit - scroll_count
        content += (
            f"\n\n--- SCROLL WARNING ({scroll_count}/{hard_limit}) ---\n"
            f"You have {remaining} scroll(s) left on this page. "
            "STOP scrolling and answer with what you have, OR use "
            "browse_page(full_page=True) to read the entire page at once.\n"
            "---\n"
        )

    return format_page_view(
        title=annotated.title,
        url=annotated.url,
        status_code=annotated.status_code,
        viewport=annotated.viewport,
        content=content,
        truncated=annotated.truncated,
    )


@emit_screenshot_after
async def go_back() -> str:
    """Navigate back in browser history and return an updated snapshot.

    Returns:
        Updated page snapshot string.

    Raises:
        BrowserToolError: If back navigation fails or no history available.
    """
    browser, view = await get_active_view("go_back")
    initial_url = view.url

    try:
        browser_result = await browser.navigate_back()
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Playwright error during go_back")
        msg = "Failed to navigate back"
        raise BrowserToolError(msg, tool="go_back") from exc

    page = await browser.current_page()
    if page.url == initial_url:
        msg = "No previous page available to navigate back to."
        raise BrowserToolError(msg, tool="go_back")

    return await _format_result(browser_result, tool_name="go_back")


@emit_screenshot_after
async def click_at(
    x1: float | int, y1: float | int, x2: float | int, y2: float | int,
) -> str:
    """Click at a random point inside a bounding box on the current page.

    Low-level coordinate tool. Prefer ``click_element`` which combines
    grounding + clicking in one step so the LLM never handles raw coordinates.

    Args:
        x1: Left edge of the bounding box (CSS pixels).
        y1: Top edge of the bounding box (CSS pixels).
        x2: Right edge of the bounding box (CSS pixels).
        y2: Bottom edge of the bounding box (CSS pixels).

    Returns:
        Updated page snapshot string.

    Raises:
        BrowserToolError: If coordinates are invalid or the click fails.
    """
    fx1, fy1, fx2, fy2 = _validate_bbox(x1, y1, x2, y2, tool_name="click_at")

    browser, view = await get_active_view("click_at")

    try:
        result = await browser.perform_interaction(lambda: human_click_at(view.frame, fx1, fy1, fx2, fy2))
        return await _format_result(result, tool_name="click_at")
    except BrowserToolError:
        raise
    except PlaywrightError as exc:  # pragma: no cover - final safety net
        logger.exception("Failed to complete click_at at bbox (%s, %s, %s, %s)", fx1, fy1, fx2, fy2)
        raise BrowserToolError("Failed to complete click_at operation", tool="click_at") from exc


@emit_screenshot_after
async def press_and_hold_at(
    x1: float | int, y1: float | int, x2: float | int, y2: float | int,
    duration_ms: int = 3000,
) -> str:
    """Press and hold at a random point inside a bounding box for a duration.

    Low-level coordinate tool. Prefer ``press_and_hold_element`` which combines
    grounding + holding in one step so the LLM never handles raw coordinates.

    Args:
        x1: Left edge of the bounding box (CSS pixels).
        y1: Top edge of the bounding box (CSS pixels).
        x2: Right edge of the bounding box (CSS pixels).
        y2: Bottom edge of the bounding box (CSS pixels).
        duration_ms: How long to hold the mouse button in milliseconds.
            Defaults to 3000 (3 seconds). Range: 500-10000.

    Returns:
        Updated page snapshot string after the hold is released.

    Raises:
        BrowserToolError: If coordinates are invalid or the hold fails.
    """
    fx1, fy1, fx2, fy2 = _validate_bbox(x1, y1, x2, y2, tool_name="press_and_hold_at")

    clamped_duration = max(500, min(10000, duration_ms))

    browser, view = await get_active_view("press_and_hold_at")

    try:
        result = await browser.perform_interaction(
            lambda: human_press_and_hold_at(view.frame, fx1, fy1, fx2, fy2, duration_ms=clamped_duration),
        )
        return await _format_result(result, tool_name="press_and_hold_at")
    except BrowserToolError:
        raise
    except PlaywrightError as exc:  # pragma: no cover - final safety net
        logger.exception("Failed to complete press_and_hold_at at bbox (%s, %s, %s, %s)", fx1, fy1, fx2, fy2)
        raise BrowserToolError(
            "Failed to complete press_and_hold_at operation",
            tool="press_and_hold_at",
        ) from exc


__all__ = [
    "click",
    "click_at",
    "drag",
    "fill_field",
    "go_back",
    "press_and_hold",
    "press_and_hold_at",
    "press_keys",
    "scroll_page",
]
