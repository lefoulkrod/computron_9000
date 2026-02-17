"""View the current page with annotated content and interactive elements.

Returns a single view combining page content and interactive elements,
annotated with ``[role] name`` markers.  The ``role:name`` pair can be
used directly as a selector in ``click()``, ``fill_field()``, and other
interaction tools.
"""

from __future__ import annotations

import logging

import tools.browser.core as browser_core
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.core.page_view import PageView, build_page_view
from tools.browser.events import emit_browser_snapshot_on_page_change

logger = logging.getLogger(__name__)


@emit_browser_snapshot_on_page_change
async def view_page(scope: str | None = None) -> PageView:
    """View the current page — no navigation, just read what's on screen.

    Returns page content interleaved with interactive element annotations.
    Each interactive element is shown as ``[role] name``, and you can use
    ``role:name`` as a selector in ``click()``, ``fill_field()``, etc.

    Example output::

        [link] Amazon
        [searchbox] Search Amazon
        [button] Go
        [h2] Results
        [link] Sony WH-1000XM5 Wireless Headphones
        $348.00
        [button] Add to Cart

    Example usage::

        view_page()                    # full viewport
        view_page(scope="Results")     # zoom into the Results section

        click("button:Add to Cart")
        fill_field("searchbox:Search Amazon", "laptop")

    Args:
        scope: Optional section name to zoom into.  Matches headings or
            landmarks by text.  Example: ``view_page(scope="Results")`` to
            see only the results section, excluding nav and sidebars.

    Returns:
        PageView with content, title, url, viewport info.

    Raises:
        BrowserToolError: If there is no open page.
    """
    try:
        browser = await browser_core.get_browser()
        page = await browser.current_page()
    except RuntimeError as exc:
        logger.debug("No current page available for view_page: %s", exc)
        raise BrowserToolError("No open page to view", tool="view_page") from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Failed to access browser for view_page")
        raise BrowserToolError("Unable to access browser pages", tool="view_page") from exc

    try:
        return await build_page_view(page, None, scope=scope)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Failed to build annotated snapshot")
        raise BrowserToolError("Failed to build page view", tool="view_page") from exc


__all__ = ["view_page"]
