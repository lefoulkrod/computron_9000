"""Browser tools: open a URL and return a PageView."""

from __future__ import annotations

import logging

import tools.browser.core as browser_core
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.core.page_view import PageView, build_page_view
from tools.browser.events import emit_browser_snapshot_on_page_change

logger = logging.getLogger(__name__)


@emit_browser_snapshot_on_page_change
async def open_url(url: str) -> PageView:
    """Open a URL in the shared browser and return an annotated page snapshot.

    Returns an annotated snapshot combining page content and interactive
    element annotations (``[role] name`` markers).  Use ``role:name`` as
    a selector in ``click()``, ``fill_field()``, etc.

    Args:
        url: The URL to open (http/https).

    Returns:
        PageView with title, url, status_code, annotated content,
        viewport info.

    Raises:
        BrowserToolError: If navigation or extraction fails.
    """
    try:
        browser = await browser_core.get_browser()
        try:
            page = await browser.current_page()
        except RuntimeError:
            page = await browser.new_page()
        response = await page.goto(url, wait_until="domcontentloaded")
        return await build_page_view(page, response)
    except Exception as exc:  # pragma: no cover - wrap into tool error
        logger.exception("Failed to open URL %s", url)
        raise BrowserToolError(str(exc), tool="open_url") from exc
