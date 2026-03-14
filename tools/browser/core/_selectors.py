"""Locator resolution utilities used by browser tools.

Resolves ref numbers from the annotated page view into Playwright locators
via ``data-ct-ref`` attribute selectors.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from playwright.async_api import (
    Error as PlaywrightError,
    Frame,
    Locator,
    Page,
)

from tools.browser.core.exceptions import BrowserToolError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _LocatorResolution:
    """Resolution metadata for a resolved locator.

    Attributes:
        locator: Playwright ``Locator`` for the resolved element.
        query: Original caller-supplied ref string.
        resolved_selector: CSS selector used to perform the lookup.
    """

    locator: Locator
    query: str
    resolved_selector: str


async def _resolve_locator(
    page: Page | Frame,
    target: str,
    *,
    tool_name: str,
) -> _LocatorResolution | None:
    """Resolve a ref number into a Playwright locator.

    The ref number corresponds to a ``data-ct-ref`` attribute stamped on
    interactive elements by the JS DOM walker during the page snapshot.

    Args:
        page: Active Playwright page or frame.
        target: Ref number as a string (e.g. ``"7"``).
        tool_name: Tool identifier used for ``BrowserToolError``.

    Returns:
        Locator resolution metadata, or ``None`` when nothing matched.

    Raises:
        BrowserToolError: On invalid input.
    """
    clean = target.strip()
    if not clean:
        raise BrowserToolError("selector must be a non-empty string", tool=tool_name)

    # Accept numeric ref strings (e.g. "7", "42")
    try:
        ref_num = int(clean)
    except ValueError:
        # Not a ref number — try as a CSS selector for backwards compatibility
        try:
            css_locator = page.locator(clean)
            count = await css_locator.count()
        except PlaywrightError:
            count = 0
        if count > 0:
            return _LocatorResolution(
                locator=css_locator.first,
                query=clean,
                resolved_selector=clean,
            )
        logger.debug("Selector '%s' is not a ref number or valid CSS selector", clean)
        return None

    selector = f'[data-ct-ref="{ref_num}"]'
    locator = page.locator(selector)

    try:
        count = await locator.count()
    except PlaywrightError as exc:
        logger.debug("Ref lookup failed for %s: %s", ref_num, exc)
        return None

    if count == 0:
        msg = (
            f"Ref {ref_num} not found on the page. "
            "The page may have changed — call browse_page() to get a fresh snapshot with updated ref numbers."
        )
        raise BrowserToolError(msg, tool=tool_name)

    return _LocatorResolution(
        locator=locator.first,
        query=clean,
        resolved_selector=selector,
    )


__all__ = [
    "_LocatorResolution",
    "_resolve_locator",
]
