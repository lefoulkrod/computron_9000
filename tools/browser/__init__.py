"""Browser tools package.

Public API:
- open_url: Open a URL and return title, url, snippet, links, forms, status_code.
- ask_about_screenshot: Capture the current page and answer a prompt about it.
- Pydantic models for returned data types.
- close_browser: Cleanly close the persistent Playwright browser.
"""

from .ask_about_screenshot import ask_about_screenshot
from .core import Browser, close_browser, get_browser
from .exceptions import BrowserToolError
from .open_url import OpenUrlForm, OpenUrlLink, OpenUrlResult

__all__ = [
    "Browser",
    "BrowserToolError",
    "OpenUrlForm",
    "OpenUrlLink",
    "OpenUrlResult",
    "ask_about_screenshot",
    "close_browser",
    "get_browser",
]
