"""Select option from dropdown tool."""

from __future__ import annotations

import logging
import random

from playwright.async_api import ElementHandle, Error as PlaywrightError, Page

from .core import get_active_view
from .core.exceptions import BrowserToolError
from .core.human import human_click, human_press_keys
from .interactions import _format_result, _resolve_or_raise

logger = logging.getLogger(__name__)

# Maximum options to navigate via keyboard before falling back to JS.
# Keeps the interaction time reasonable for long option lists.
_MAX_KEYBOARD_NAV_STEPS = 30

# Maximum time (ms) to wait for dynamically-populated options to appear
# after clicking an empty dropdown.
_POPULATION_WAIT_MS = 2000


async def _keyboard_select(
    page: Page,
    select_handle: ElementHandle,
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
        await human_press_keys(page, ["Home"])
        await page.wait_for_timeout(random.randint(30, 80))

        # Navigate down to the target option
        for _ in range(target_index):
            await human_press_keys(page, ["ArrowDown"])
            await page.wait_for_timeout(random.randint(20, 60))

        # Confirm selection
        await human_press_keys(page, ["Enter"])
        await page.wait_for_timeout(random.randint(50, 150))

        # Verify the native <select> actually changed
        actual_index = await select_handle.evaluate("el => el.selectedIndex")
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


async def _js_select(select_handle: ElementHandle, target_index: int) -> None:
    """Fall back to setting selectedIndex via JS with synthetic events.

    Event dispatch is wrapped in try/catch because some pages' handlers
    assume internal state from a real native interaction and can throw.
    """
    await select_handle.evaluate(
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


async def _populate_dropdown_options(
    select_locator,
    page: Page,
    view,
) -> list[str]:
    """Click a dropdown to trigger JS population, then re-read options.

    Some dropdowns (e.g. X/Twitter signup date-of-birth) are empty until
    the user clicks them, which triggers JavaScript to populate the
    ``<option>`` elements.  This function clicks the dropdown, waits
    for options to appear, and returns the populated option list.

    Args:
        select_locator: Playwright locator for the ``<select>`` element.
        page: The Playwright Page for wait_for_timeout calls.
        view: The ActiveView for human_click calls.

    Returns:
        List of option text strings after population attempt.
    """
    logger.debug("Dropdown appears empty; clicking to trigger JS population")
    await human_click(view.frame, select_locator)
    await page.wait_for_timeout(random.randint(300, 600))

    # Wait for options to appear
    try:
        await select_locator.locator("option").first.wait_for(
            state="attached", timeout=_POPULATION_WAIT_MS,
        )
    except PlaywrightError:
        logger.debug("No options appeared after clicking dropdown")

    # Re-read options after population
    options = [o.strip() for o in await select_locator.locator("option").all_text_contents()]
    logger.debug("After click, dropdown has %d options", len(options))
    return options


def _find_option_index(options: list[str], value: str) -> int:
    """Find the index of an option value, with fuzzy matching fallback.

    Tries exact match first, then falls back to case-insensitive and
    whitespace-normalized matching.  Some sites add extra whitespace
    or formatting to option text that doesn't match the displayed value.

    Args:
        options: List of option text strings.
        value: The desired option text to find.

    Returns:
        The index of the matching option.

    Raises:
        ValueError: If no matching option is found.
    """
    # Exact match
    try:
        return options.index(value)
    except ValueError:
        pass

    # Case-insensitive and whitespace-normalized match
    normalized = value.strip().lower()
    for i, opt in enumerate(options):
        if opt.strip().lower() == normalized:
            return i

    raise ValueError(f"Option '{value}' not found in dropdown")


async def select_option(selector: str, value: str, wait_after_select_ms: int | None = None) -> str:
    """Select an option from a ``<select>`` dropdown by visible text.

    Handles both native ``<select>`` elements and dynamically-populated
    dropdowns where options are loaded via JavaScript after the dropdown
    is opened (e.g. X/Twitter signup date-of-birth dropdowns, AJAX
    search selects).

    Args:
        selector: Ref number from ``browse_page()`` output.
            Examples: ``"7"``, ``"12"``.
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
        # Resolve selector using shared resolution (ref number from page view).
        resolution = await _resolve_or_raise(view.frame, selector.strip(), tool_name="select_option")

        select_locator = resolution.locator

        # Get all options to find the index of the desired value
        options = [o.strip() for o in await select_locator.locator("option").all_text_contents()]

        # BTI-012: If the dropdown appears empty, click it to trigger
        # JavaScript population (common on signup forms like X/Twitter),
        # then re-read options after a short wait.
        if not options:
            page = await browser.current_page()
            options = await _populate_dropdown_options(select_locator, page, view)

        # Find the target option index with fuzzy matching fallback
        try:
            target_index = _find_option_index(options, value)
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
        return await _format_result(browser_result)
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Failed to select option '%s' from '%s'", value, selector)
        msg = f"Failed to select option '{value}' from dropdown '{selector}'"
        raise BrowserToolError(msg, tool="select_option") from exc


__all__ = ["select_option"]