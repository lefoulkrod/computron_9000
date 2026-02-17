"""Select option from dropdown tool."""

from __future__ import annotations

import logging
import random

from playwright.async_api import Error as PlaywrightError

from .core._selectors import _resolve_locator
from .core.browser import get_browser
from .core.exceptions import BrowserToolError
from .core.human import human_click, human_press_keys
from .interactions import InteractionResult, _build_snapshot

logger = logging.getLogger(__name__)


async def select_option(selector: str, value: str, wait_after_select_ms: int | None = None) -> InteractionResult:
    """Select an option from a <select> dropdown by visible text.

    Automatically handles HTML <select> elements with human-like interaction:
    clicks to open, navigates with arrow keys, presses Enter to select.

    Supports bare role selectors for dropdowns without an accessible name::

        select_option("combobox", "Newest")          # bare role
        select_option("combobox:", "Newest")          # trailing colon also works
        select_option("combobox:Sort by", "Newest")   # role:name when labelled

    Args:
        selector: Element selector in ``role:name`` format from snapshot output,
            bare role (e.g. ``"combobox"``), or CSS selector.
        value: Exact visible text of the option to select (case-sensitive).
            Example: "Newest" or "Price: Low to High".
        wait_after_select_ms: Optional milliseconds to wait after selecting (for page updates).

    Returns:
        InteractionResult: Change metadata plus snapshot if page changed.

    Raises:
        BrowserToolError: If dropdown not found, option text doesn't match, or selection fails.

    Example:
        # From snapshot: [combobox] Sort by = Newest
        result = select_option("combobox:Sort by", "Price: Low to High")
    """
    logger.info("Selecting option '%s' from dropdown '%s'", value, selector)

    try:
        browser = await get_browser()
        page = await browser.current_page()
    except (PlaywrightError, RuntimeError) as exc:
        logger.exception("Unable to access browser page for select_option")
        msg = "Unable to access browser page"
        raise BrowserToolError(msg, tool="select_option") from exc

    if page.url in {"", "about:blank"}:
        msg = "Navigate to a page before attempting to select options."
        raise BrowserToolError(msg, tool="select_option")

    try:
        # Resolve selector using shared resolution (supports role:name and
        # bare role formats like "combobox" for unlabelled dropdowns).
        resolution = await _resolve_locator(
            page,
            selector.strip(),
            allow_substring_text=False,
            require_single_match=True,
            tool_name="select_option",
        )
        if resolution is None:
            msg = f"No element found matching selector '{selector}'."
            raise BrowserToolError(msg, tool="select_option")

        select_locator = resolution.locator

        # First, get all options to find the index of the desired value
        options = await select_locator.locator("option").all_text_contents()
        try:
            target_index = options.index(value)
        except ValueError as exc:
            msg = f"Option '{value}' not found in dropdown. Available options: {options}"
            raise BrowserToolError(msg, tool="select_option") from exc

        # Get currently selected index
        current_value = await select_locator.input_value()
        option_values = await select_locator.locator("option").evaluate_all("options => options.map(o => o.value)")
        try:
            current_index = option_values.index(current_value) if current_value else 0
        except ValueError:
            current_index = 0

        # Define the selection action with human-like behavior
        async def _perform_select() -> None:
            # Step 1: Click the select element to open it (human-like with mouse movement)
            await human_click(page, select_locator)

            # Step 2: Brief pause (human reading options) - 100-300ms
            await page.wait_for_timeout(random.randint(100, 300))

            # Step 3: Navigate to the option using arrow keys
            # Calculate how many arrow key presses needed
            steps = target_index - current_index

            if steps > 0:
                # Press ArrowDown to move forward
                keys = ["ArrowDown"] * steps
            elif steps < 0:
                # Press ArrowUp to move backward
                keys = ["ArrowUp"] * abs(steps)
            else:
                # Already on the right option, just press Enter
                keys = []

            if keys:
                await human_press_keys(page, keys)
                # Brief pause after navigation - 50-150ms
                await page.wait_for_timeout(random.randint(50, 150))

            # Step 4: Press Enter to select
            await human_press_keys(page, ["Enter"])

            # Step 5: Optional additional wait
            if wait_after_select_ms:
                await page.wait_for_timeout(wait_after_select_ms)

        # Perform interaction and check for page changes
        browser_result = await browser.perform_interaction(page, _perform_select)
        annotated = None
        if browser_result.page_changed:
            annotated = await _build_snapshot(page, browser_result.navigation_response)

        logger.info("Select option result: %s", browser_result.reason)
        return InteractionResult(
            page_view=annotated,
            page_changed=browser_result.page_changed,
            reason=browser_result.reason,
        )
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Failed to select option '%s' from '%s'", value, selector)
        msg = f"Failed to select option '{value}' from dropdown '{selector}'"
        raise BrowserToolError(msg, tool="select_option") from exc


__all__ = ["select_option"]
