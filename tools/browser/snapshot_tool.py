"""Browse the current page with annotated content and interactive elements.

Returns a single view combining page content and interactive elements,
annotated with ``[ref] [role] name`` markers.  Pass the ref number to
``click()``, ``fill_field()``, and other interaction tools.
"""

from __future__ import annotations

import logging

from tools.browser.core import get_active_view
from tools.browser.core._formatting import format_page_view
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.core.page_view import build_page_view
from tools.browser.events import emit_screenshot_after

logger = logging.getLogger(__name__)


@emit_screenshot_after
async def browse_page(scope: str | None = None, full_page: bool = False) -> str:
    """See interactive elements on the current page with ref numbers.

    Use this when you need to INTERACT: find buttons, links, forms, and get
    ref numbers for ``click()``, ``fill_field()``, etc.  For reading text
    content, use ``read_page()`` instead.  After click/fill/scroll, the
    page_view is returned automatically — only call ``browse_page()`` to
    re-examine without acting.

    Output format — each element shown as ``[ref] [role] name``::

        [3] [searchbox] Search Amazon
        [4] [link] Sony WH-1000XM5
        $348.00
        [5] [button] Add to Cart

    Use the ref number as selector::

        click("5")
        fill_field("3", "laptop")

    Args:
        scope: Narrow to a section by heading or landmark text.  Example:
            ``browse_page(scope="Results")`` to skip nav and sidebars.
            Respects viewport clipping — combine with ``full_page=True``
            for off-screen sections.
        full_page: Show all elements, not just the current viewport.
            Useful for finding elements without scrolling.  Long pages
            may be truncated.

    Returns:
        Formatted string with page header, viewport info, and annotated content.

    Raises:
        BrowserToolError: If there is no open page.
    """
    _, view = await get_active_view("browse_page")

    try:
        pv = await build_page_view(view, None, scope=scope, full_page=full_page)
        return format_page_view(
            title=pv.title,
            url=pv.url,
            status_code=pv.status_code,
            viewport=pv.viewport,
            content=pv.content,
            truncated=pv.truncated,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Failed to build annotated snapshot")
        raise BrowserToolError("Failed to build page view", tool="browse_page") from exc


__all__ = ["browse_page"]
