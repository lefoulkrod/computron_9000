"""Browser tools package.

Public API:
- open_url: Open a URL and return title, url, snippet, links, forms, status_code.
- ask_about_screenshot: Capture the current page and answer a prompt about it.
- Pydantic models for returned data types.
- close_browser: Cleanly close the persistent Playwright browser.
"""

from .ask_about_screenshot import ask_about_screenshot
from .core import Browser, close_browser, get_browser
from .core.snapshot import Form, Link, PageSnapshot
from .exceptions import BrowserToolError
from .open import open_url

__all__ = [
    "Browser",
    "BrowserToolError",
    "Form",
    "Link",
    "PageSnapshot",
    "ask_about_screenshot",
    "close_browser",
    "get_browser",
    "open_url",
]
