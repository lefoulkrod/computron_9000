"""Browser tools package.

Public API:
- open_url: Open a URL and return title, url, snippet, links, forms, status_code.
- OpenUrlResult, OpenUrlLink, OpenUrlForm: Pydantic models for results.
- close_browser: Cleanly close the persistent Playwright browser.
"""

from .core import Browser, close_browser, get_browser
from .open_url import BrowserToolError, OpenUrlForm, OpenUrlLink, OpenUrlResult

__all__ = [
    "Browser",
    "BrowserToolError",
    "OpenUrlForm",
    "OpenUrlLink",
    "OpenUrlResult",
    "close_browser",
    "get_browser",
]
