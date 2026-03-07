"""Browser tools: open a URL and return an annotated page snapshot."""

from __future__ import annotations

import logging

import tools.browser.core as browser_core
from tools.browser.core._formatting import format_page_view
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.core.page_view import build_page_view
from tools.browser.events import emit_screenshot_after

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

        if result.download is not None:
            return format_page_view(
                title="File Download",
                url=url,
                status_code=200,
                content="",
                viewport=None,
                truncated=False,
                downloaded_file=result.download,
            )

        view = await browser.active_view()
        pv = await build_page_view(view, result.navigation_response)
        return format_page_view(
            title=pv.title,
            url=pv.url,
            status_code=pv.status_code,
            viewport=pv.viewport,
            content=pv.content,
            truncated=pv.truncated,
            downloaded_file=pv.downloaded_file,
        )
    except BrowserToolError:
        raise
    except Exception as exc:  # pragma: no cover - wrap into tool error
        logger.exception("Failed to open URL %s", url)
        raise BrowserToolError(str(exc), tool="open_url") from exc
