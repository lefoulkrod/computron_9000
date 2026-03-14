"""Browser tools: open a URL and return an annotated page snapshot."""

from __future__ import annotations

import logging

import tools.browser.core as browser_core
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.events import emit_screenshot_after
from tools.browser.interactions import _format_result

logger = logging.getLogger(__name__)


@emit_screenshot_after
async def open_url(url: str) -> str:
    """Navigate to a URL and return an annotated page snapshot.

    Opens the URL and returns page content with ``[role] name`` markers for
    interactive elements.  To re-examine the current page without navigating,
    use ``browse_page()`` instead.

    Args:
        url: The URL to navigate to.

    Returns:
        Formatted string with page header, viewport info, and annotated content.

    Raises:
        BrowserToolError: If navigation or extraction fails.
    """
    try:
        browser = await browser_core.get_browser()
        result = await browser.navigate(url)
        return await _format_result(result)
    except BrowserToolError:
        raise
    except Exception as exc:  # pragma: no cover - wrap into tool error
        logger.exception("Failed to open URL %s", url)
        raise BrowserToolError(str(exc), tool="open_url") from exc


__all__ = ["open_url"]
