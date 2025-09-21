"""Browser tool: open a URL and return a lightweight page snapshot.

Implementation delegates snapshot extraction to shared internal helper
``_build_page_snapshot`` located in ``tools.browser.core.snapshot`` so
other tools can re-use consistent snapshot semantics.
"""

from __future__ import annotations

import logging

import tools.browser.core as browser_core
from tools.browser.core.exceptions import BrowserToolError
from tools.browser.core.snapshot import PageSnapshot, _build_page_snapshot

logger = logging.getLogger(__name__)


# NOTE: Link/Form/PageSnapshot now live in tools.browser.core.snapshot.
# If external callers previously imported them from this module they should
# update imports. We intentionally do not re-export to keep surface minimal.


async def open_url(url: str) -> PageSnapshot:  # backward-compatible function name
    """Open a URL in the shared browser and return a compact snapshot.

    Args:
        url: The URL to open (http/https).

    Returns:
        PageSnapshot: Pydantic model with title, url, snippet, links, forms, status_code.

    Raises:
        BrowserToolError: If navigation or extraction fails.
    """
    try:
        # Access via module attribute so tests can monkeypatch tools.browser.core.get_browser
        browser = await browser_core.get_browser()
        page = await browser.new_page()
        response = await page.goto(url, wait_until="domcontentloaded")
        return await _build_page_snapshot(page, response)
    except Exception as exc:  # pragma: no cover - wrap into tool error
        logger.exception("Failed to open URL %s", url)
        raise BrowserToolError(str(exc), tool="open_url") from exc


async def current_page() -> PageSnapshot:
    """Return a snapshot of the currently open page without creating a new one.

    This tool inspects the existing pages in the persistent Playwright
    ``BrowserContext`` and returns a lightweight ``PageSnapshot`` of the most
    recently opened, still-open page. Unlike ``Browser.current_page()`` it does
    NOT create a new page if none are available; instead it raises a
    ``BrowserToolError`` so callers can decide how to proceed (e.g., open a URL
    first).

    Returns:
        PageSnapshot: Structured snapshot of the active page.

    Raises:
        BrowserToolError: If there is no open page or if snapshot extraction
            fails for any reason.
    """
    try:
        browser = await browser_core.get_browser()
        page = await browser.current_page()  # will raise RuntimeError if none
    except RuntimeError as exc:
        logger.debug("No current page available: %s", exc)
        msg = "No open page to snapshot"
        raise BrowserToolError(msg, tool="current_page") from exc
    except Exception as exc:  # pragma: no cover - defensive broad guard
        logger.exception("Failed to access browser for current page snapshot")
        msg = "Unable to access browser pages"
        raise BrowserToolError(msg, tool="current_page") from exc

    try:
        return await _build_page_snapshot(page, None)
    except Exception as exc:  # pragma: no cover - wrap into tool error
        logger.exception("Failed to build snapshot of current page")
        msg = "Failed to snapshot current page"
        raise BrowserToolError(msg, tool="current_page") from exc
