"""Core browser components for web-browsing tools.

Public API:
- _Browser: minimal persistent Playwright browser core
"""

from playwright.async_api import Error as PlaywrightError

from .browser import ActiveView, Browser, PageOrFrame, close_browser, get_browser
from .exceptions import BrowserToolError
from ._file_detection import DownloadInfo

__all__ = [
    "ActiveView",
    "Browser",
    "DownloadInfo",
    "PageOrFrame",
    "close_browser",
    "get_browser",
    "get_active_view",
]


async def get_active_view(tool_name: str) -> tuple[Browser, ActiveView]:
    """Get the browser and active view, raising ``BrowserToolError`` if unavailable.

    Replaces the repeated boilerplate of ``get_browser()`` + ``current_page()``
    + URL check + ``active_frame()`` that every browser tool previously had.
    """
    try:
        browser = await get_browser()
        view = await browser.active_view()
    except (PlaywrightError, RuntimeError) as exc:
        raise BrowserToolError(
            "Unable to access browser page", tool=tool_name,
        ) from exc
    if view.url in {"", "about:blank"}:
        raise BrowserToolError("Navigate to a page first.", tool=tool_name)
    return browser, view
