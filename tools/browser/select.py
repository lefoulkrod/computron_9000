"""Select option from dropdown tool."""

from __future__ import annotations

import logging
import random

from playwright.async_api import Error as PlaywrightError

from .core import get_active_view
from .core._formatting import format_interaction_result, format_page_view
from .core._selectors import _resolve_locator
from .core.exceptions import BrowserToolError
from .core.human import human_click, human_press_keys
from .interactions import _build_snapshot

logger = logging.getLogger(__name__)

# Maximum options to navigate via keyboard before falling back to JS.
# Keeps the interaction time reasonable for long option lists.
_MAX_KEYBOARD_NAV_STEPS = 30


async def _keyboard_select(
    page: object,
    select_handle: object,
    target_index: int,
) -> bool:
    """Try to select an option using keyboard navigation (trusted events).

    Presses Home to reset to first option, then ArrowDown × target_index,
    then Enter.  All key presses generate ``isTrusted: true`` events.

    Returns ``True`` if the native ``<select>`` element's ``selectedIndex``
    matches ``target_index`` after navigation, ``False`` otherwise.
    """
    if target_index > _MAX_KEYBOARD_NAV_STEPS:
        logger.debug(
            "Target index %d exceeds keyboard nav limit %d; skipping keyboard approach",
            target_index,
            _MAX_KEYBOARD_NAV_STEPS,
        )
        return False

    try:
        # Home resets to the first option in a native <select>.
        await human_press_keys(page, ["Home"])  # type: ignore[arg-type]
        await page.wait_for_timeout(random.randint(30, 80))  # type: ignore[union-attr]

        # Navigate down to the target option
        for _ in range(target_index):
            await human_press_keys(page, ["ArrowDown"])  # type: ignore[arg-type]
            await page.wait_for_timeout(random.randint(20, 60))  # type: ignore[union-attr]

        # Confirm selection
        await human_press_keys(page, ["Enter"])  # type: ignore[arg-type]
        await page.wait_for_timeout(random.randint(50, 150))  # type: ignore[union-attr]

        # Verify the native <select> actually changed
        actual_index = await select_handle.evaluate("el => el.selectedIndex")  # type: ignore[union-attr]
        if actual_index == target_index:
            logger.debug("Keyboard navigation succeeded: selectedIndex=%d", actual_index)
            return True

        logger.debug(
            "Keyboard navigation landed on index %d instead of %d; will fall back to JS",
            actual_index,
            target_index,
        )
        return False
    except (PlaywrightError, Exception) as exc:
        logger.debug("Keyboard navigation failed: %s", exc)
        return False


async def _js_select(select_handle: object, target_index: int) -> None:
    """Fall back to setting selectedIndex via JS with synthetic events.

    Event dispatch is wrapped in try/catch because some pages' handlers
    assume internal state from a real native interaction and can throw.
    """
    await select_handle.evaluate(  # type: ignore[union-attr]
        """(el, idx) => {
            el.selectedIndex = idx;
            try {
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            } catch (_) {
                // Page-side handler errors should not prevent selection.
            }
        }""",
        target_index,
    )


async def select_option(selector: str, value: str, wait_after_select_ms: int | None = None) -> str:
    """Select an option from a ``<select>`` dropdown by visible text.

    Args:
        selector: ``role:name`` selector for the dropdown.  Examples:
            ``"combobox:Sort by"``, ``"combobox"`` (bare role for unlabelled).
        value: Exact visible text of the option (case-sensitive).
            Example: ``"Price: Low to High"``.
        wait_after_select_ms: Optional ms to wait after selecting.

    Returns:
        Formatted string with action header and page snapshot.

    Raises:
        BrowserToolError: If dropdown not found or option text doesn't match.
    """
    logger.info("Selecting option '%s' from dropdown '%s'", value, selector)

    browser, view = await get_active_view("select_option")

    try:
        # Resolve selector using shared resolution (supports role:name and
        # bare role formats like "combobox" for unlabelled dropdowns).
        resolution = await _resolve_locator(
            view.frame,
            selector.strip(),
            allow_substring_text=False,
            require_single_match=True,
            tool_name="select_option",
        )
        if resolution is None:
            msg = f"No element found matching selector '{selector}'."
            raise BrowserToolError(msg, tool="select_option")

        select_locator = resolution.locator

        # Get all options to find the index of the desired value
        options = [o.strip() for o in await select_locator.locator("option").all_text_contents()]
        try:
            target_index = options.index(value)
        except ValueError as exc:
            msg = f"Option '{value}' not found in dropdown. Available options: {options}"
            raise BrowserToolError(msg, tool="select_option") from exc

        # Pin an ElementHandle so DOM changes (e.g. custom overlay opening)
        # don't invalidate our reference — positional locators like .nth(1)
        # break when the page adds/removes elements.
        select_handle = await select_locator.element_handle(timeout=5000)

        # Get the page for wait_for_timeout calls
        page = await browser.current_page()

        async def _perform_select() -> None:
            # Click the dropdown to open it (human-like mouse movement).
            await human_click(view.frame, select_locator)
            await page.wait_for_timeout(random.randint(100, 300))

            # Try keyboard navigation first — generates isTrusted:true events
            # that avoid bot detection.  Falls back to JS if the keyboard
            # approach doesn't land on the right option (custom overlays can
            # intercept keys and shift the cursor unpredictably).
            # _keyboard_select needs a Page (not Frame) for wait_for_timeout
            kb_ok = await _keyboard_select(page, select_handle, target_index)

            if not kb_ok:
                logger.debug("Falling back to JS selectedIndex for '%s'", value)
                await _js_select(select_handle, target_index)
                # Close any open overlay
                await human_press_keys(view.frame, ["Escape"])
            # else: keyboard Enter already closed the dropdown

            if wait_after_select_ms:
                await page.wait_for_timeout(wait_after_select_ms)

        # Perform interaction and check for page changes
        browser_result = await browser.perform_interaction(_perform_select)

        if browser_result.download is not None:
            pv_str = format_page_view(
                title="File Download",
                url="",
                status_code=200,
                content="",
                viewport=None,
                truncated=False,
                downloaded_file=browser_result.download,
            )
            return format_interaction_result(
                reason=browser_result.reason,
                page_changed=browser_result.page_changed,
                page_view_str=pv_str,
            )

        pv_str = None
        if browser_result.page_changed:
            annotated = await _build_snapshot(browser_result.navigation_response)
            pv_str = format_page_view(
                title=annotated.title,
                url=annotated.url,
                status_code=annotated.status_code,
                viewport=annotated.viewport,
                content=annotated.content,
                truncated=annotated.truncated,
            )

        logger.info("Select option result: %s", browser_result.reason)
        return format_interaction_result(
            reason=browser_result.reason,
            page_changed=browser_result.page_changed,
            page_view_str=pv_str,
        )
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Failed to select option '%s' from '%s'", value, selector)
        msg = f"Failed to select option '{value}' from dropdown '{selector}'"
        raise BrowserToolError(msg, tool="select_option") from exc


__all__ = ["select_option"]
