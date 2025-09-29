"""Browser tools package.

Important: the browser used by these tools is long-lived within the process
and maintains browser state between tool calls. This includes cookies,
localStorage/sessionStorage, open pages/tabs, and other session-specific
state. Call ``close_browser`` (or restart the process) to fully reset the
browser and clear that state when needed.

Public API:
- open_url: Open a URL and return title, url, snippet, elements, status_code.
- ask_about_screenshot: Capture the current page and answer a prompt about it.
- Pydantic models for returned data types.
- close_browser: Cleanly close the persistent Playwright browser.
"""

from .ask_about_screenshot import ask_about_screenshot
from .core import Browser, close_browser, get_browser
from .core.exceptions import BrowserToolError
from .core.snapshot import Element, PageSnapshot
from .interactions import click, fill_field, press_keys
from .page import current_page, open_url
from .search import TextExtractionResult, extract_text

__all__ = [
    "Browser",
    "BrowserToolError",
    "Element",
    "PageSnapshot",
    "TextExtractionResult",
    "ask_about_screenshot",
    "click",
    "close_browser",
    "current_page",
    "extract_text",
    "fill_field",
    "get_browser",
    "open_url",
    "press_keys",
]
