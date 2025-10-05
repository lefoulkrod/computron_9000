"""Browser interaction tools.

This module exposes helpers for interacting with the active browser page. The
``click`` function clicks an element specified by visible text or a selector
handle and returns a fresh ``PageSnapshot`` of the active page. The ``fill_field``
function enters text into an input or textarea located by the shared selector
resolution helper and also returns an updated ``PageSnapshot``.
"""

from __future__ import annotations

import logging

from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    Page,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from config import BrowserWaitConfig, load_config
from tools.browser.core import get_browser
from tools.browser.core._selectors import _LocatorResolution, _resolve_locator
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.core.human import (
    human_click,
    human_press_keys,
    human_scroll,
    human_type,
)
from tools.browser.core.snapshot import PageSnapshot, _build_page_snapshot

logger = logging.getLogger(__name__)


async def _wait_for_page_settle(
    page: Page,
    *,
    expect_navigation: bool,
    waits: BrowserWaitConfig,
) -> None:
    """Wait for a page to settle after an interaction.

    This first optionally waits for network idle after navigation, then waits
    for DOM mutations to quiet down for a short period. Timeouts are bounded
    by values in ``waits``. Any timeout or Playwright error is logged and the
    function returns so callers can continue (best-effort settling).
    """
    try:
        if expect_navigation:
            # Some test fakes may not implement wait_for_load_state; be permissive.
            if hasattr(page, "wait_for_load_state"):
                try:
                    # Wait for network activity to quiet down after navigation
                    await page.wait_for_load_state(
                        "networkidle",
                        timeout=waits.post_navigation_idle_timeout_ms,
                    )
                except PlaywrightTimeoutError:
                    logger.debug(
                        "post-navigation networkidle wait timed out after %d ms",
                        waits.post_navigation_idle_timeout_ms,
                    )
            else:
                logger.debug("Page object has no wait_for_load_state; skipping networkidle wait")

        # Wait for DOM mutations to be quiet for the configured window, but bound by dom_mutation_timeout_ms.
        dom_quiet_ms = max(0, waits.dom_quiet_window_ms)
        js = f"""() => {{
            return new Promise((resolve) => {{
                const quiet = {dom_quiet_ms};
                let timer = setTimeout(() => {{ resolve(true); }}, quiet);
                const obs = new MutationObserver(() => {{
                    clearTimeout(timer);
                    timer = setTimeout(() => {{ obs.disconnect(); resolve(true); }}, quiet);
                }});
                try {{
                    obs.observe(document, {{ childList: true, subtree: true, attributes: true, characterData: true }});
                }} catch (e) {{
                    // If observing fails (e.g., about:blank), resolve immediately
                    clearTimeout(timer);
                    resolve(true);
                }}
            }});
        }}"""

        # If the page stub doesn't implement wait_for_function (tests), skip the JS observer
        if hasattr(page, "wait_for_function"):
            try:
                await page.wait_for_function(js, timeout=waits.dom_mutation_timeout_ms)
            except PlaywrightTimeoutError:
                logger.debug(
                    "DOM mutation quiet wait timed out after %d ms",
                    waits.dom_mutation_timeout_ms,
                )
        else:
            logger.debug("Page object has no wait_for_function; skipping DOM quiet wait")
    except PlaywrightError as exc:
        logger.debug("Error while waiting for page settle: %s", exc)
    return None


async def click(selector: str) -> PageSnapshot:
    """Click an element by visible text or selector handle and snapshot the page.

    Args:
        selector: Either a visible text string (e.g. ``"Book Now"``) or a selector
            handle (for example a CSS selector string like ``"button#submit"`` or
            an internal selector handle returned in page snapshots). Leading and
            trailing whitespace is ignored for text matching. Prefer passing the
            element's `selector` from page snapshots; fall back to visible text only
            when no selector is available.

    Returns:
        PageSnapshot: Structured snapshot of the page after performing the click.

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

    # Attempt click & detect navigation (best-effort)
    response = None
    # Load wait configuration
    wait_cfg = load_config().tools.browser.waits

    try:
        try:
            # Short timeout: many clicks won't navigate; use configured navigation timeout
            # Perform the click inside the expect_navigation context so we only click once.
            async with page.expect_navigation(
                wait_until="domcontentloaded",
                timeout=wait_cfg.navigation_timeout_ms,
            ) as nav_ctx:
                await human_click(page, locator)
            # nav_ctx.value is an awaitable returning a Response
            response = await nav_ctx.value
            # Allow the page to settle after navigation
            await _wait_for_page_settle(page, expect_navigation=True, waits=wait_cfg)
        except PlaywrightTimeoutError:
            # Navigation wait timed out. The click already fired inside the
            # expect_navigation context, so skip a second click and only allow
            # the page to settle for SPA updates.
            await _wait_for_page_settle(page, expect_navigation=False, waits=wait_cfg)
        except PlaywrightError as exc:
            logger.exception("Playwright error during click for selector %s", clean_selector)
            msg = f"Playwright error clicking element: {exc}"
            raise BrowserToolError(msg, tool="click", details=details) from exc

        # Build snapshot (response may be None if no navigation)
        return await _build_page_snapshot(page, response)
    except BrowserToolError:
        raise  # already wrapped
    except PlaywrightError as exc:  # pragma: no cover - final safety net
        logger.exception("Failed to build snapshot after click for selector %s", clean_selector)
        msg = "Failed to complete click operation"
        raise BrowserToolError(msg, tool="click", details=details) from exc


async def fill_field(selector: str, value: str | int | float | bool | None) -> PageSnapshot:
    """Type into a text-like input located by visible text or selector handle.

    Args:
        selector: Visible text or selector handle identifying the input element. Prefer
            the `selector` field from page snapshots and fall back to visible text.
        value: Textual value (converted to string) to type into the control.

    Returns:
        PageSnapshot: Snapshot of the page after the fill operation completes.

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
        handle = await locator.element_handle()
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

    try:
        await human_click(page, locator)
        await human_type(page, locator, text_value, clear_existing=True)
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Playwright error during fill_field for selector %s", clean_selector)
        msg = f"Playwright error filling element: {exc}"
        raise BrowserToolError(msg, tool="fill_field", details=details) from exc
    # Allow SPA updates to settle before snapshotting
    wait_cfg = load_config().tools.browser.waits
    await _wait_for_page_settle(page, expect_navigation=False, waits=wait_cfg)

    return await _build_page_snapshot(page, None)


__all__ = ["click", "fill_field"]


async def press_keys(keys: list[str]) -> PageSnapshot:
    """Press one or more keyboard keys in order and return an updated page snapshot.

    Args:
        keys: Ordered list of key names (for example: "Enter", "Escape", "ArrowDown",
            or modifier chords such as "Control+Shift+P"). Keys are applied to the
            currently focused element on the active page.

    Returns:
        PageSnapshot: Snapshot of the page state after the keys are pressed.

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

    try:
        # Delegate to human helper which performs the low-level keyboard operations
        await human_press_keys(page, keys)
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Playwright error during press_keys for keys %s", keys)
        msg = f"Playwright error pressing keys: {exc}"
        raise BrowserToolError(msg, tool="press_keys") from exc

    wait_cfg = load_config().tools.browser.waits
    await _wait_for_page_settle(page, expect_navigation=False, waits=wait_cfg)
    return await _build_page_snapshot(page, None)


__all__.append("press_keys")


async def scroll_page(direction: str = "down", amount: int | None = None) -> PageSnapshot:
    """Scroll the page in the given direction and return the updated page snapshot.

    Args:
        direction: One of {"down", "up", "page_down", "page_up", "top", "bottom"}.
        amount: Optional pixel distance for fine-grained scrolling when direction
            is "down" or "up". If omitted, a viewport-sized scroll is performed.

    Returns:
        PageSnapshot: Snapshot of the page state after scrolling.

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

    try:
        # delegate low-level scrolling to human helper
        await human_scroll(page, direction=direction, amount=amount)
    except BrowserToolError:
        raise
    except PlaywrightError as exc:
        logger.exception("Playwright error during scroll_page for direction %s", direction)
        raise BrowserToolError(f"Playwright error performing scroll: {exc}", tool="scroll_page") from exc

    wait_cfg = load_config().tools.browser.waits
    await _wait_for_page_settle(page, expect_navigation=False, waits=wait_cfg)
    return await _build_page_snapshot(page, None)


__all__.append("scroll_page")
