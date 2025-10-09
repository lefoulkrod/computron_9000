"""Browser tools package.

Important: the browser used by these tools is long-lived within the process
and maintains browser state between tool calls. This includes cookies,
localStorage/sessionStorage, open pages/tabs, and other session-specific
state. Call ``close_browser`` (or restart the process) to fully reset the
browser and clear that state when needed.

Public API:
- open_url: Open a URL and return title, url, snippet, elements, status_code.
- ask_about_screenshot: Capture the current page and answer a prompt about it.
- ground_elements_by_text: Locate UI elements matching visible text via the vision model.
- Pydantic models for returned data types.
- close_browser: Cleanly close the persistent Playwright browser.
"""

from .core import Browser, close_browser, get_browser
from .core.exceptions import BrowserToolError
from .core.snapshot import Element, PageSnapshot
from .interactions import click, drag, fill_field, press_keys, scroll_page
from .page import current_page, list_clickable_elements, open_url
from .search import TextExtractionResult, extract_text
from .vision import GroundingResult, ask_about_screenshot, ground_elements_by_text

__all__ = [
    "Browser",
    "BrowserToolError",
    "Element",
    "GroundingResult",
    "PageSnapshot",
    "TextExtractionResult",
    "ask_about_screenshot",
    "click",
    "drag",
    "close_browser",
    "current_page",
    "extract_text",
    "fill_field",
    "get_browser",
    "ground_elements_by_text",
    "list_clickable_elements",
    "open_url",
    "press_keys",
    "scroll_page",
]
