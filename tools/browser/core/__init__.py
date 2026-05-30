"""Core browser components for web-browsing tools.

Public API:
- _Browser: minimal persistent Playwright browser core
"""

from playwright.async_api import Error as PlaywrightError

from .browser import ActiveView, Browser, PageOrFrame, close_browser, get_browser, release_agent_browser
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
    "release_agent_browser",
]


async def get_active_view(
    tool_name: str, *, tab: str,
) -> tuple[Browser, ActiveView]:
    """Get the browser and active view for *tab*.

    Resolves *tab* via :meth:`Browser.resolve_tab`.  Raises
    ``BrowserToolError`` when *tab* doesn't resolve to an open tab.
    """
    try:
        browser = await get_browser()
        page = browser.resolve_tab(tab)
        view = await browser.active_view(page=page)
    except ValueError as exc:
        raise BrowserToolError(str(exc), tool=tool_name) from exc
    except (PlaywrightError, RuntimeError) as exc:
        raise BrowserToolError(
            "Unable to access browser page", tool=tool_name,
        ) from exc
    if view.url in {"", "about:blank"}:
        raise BrowserToolError("Navigate to a page first.", tool=tool_name)
    return browser, view
