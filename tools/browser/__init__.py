"""Browser tools package.

Important: the browser used by these tools is long-lived within the process
and maintains browser state between tool calls. This includes cookies,
localStorage/sessionStorage, open pages/tabs, and other session-specific
state. Call ``close_browser`` (or restart the process) to fully reset the
browser and clear that state when needed.

Public API:
- open_url: Navigate to a URL and return a PageView.
- view_page: View the current page (no navigation) with ``[role] name``
  markers for interactive elements.  Optional ``scope`` parameter to focus
  on a specific section.
- click, fill_field, press_keys, select_option, scroll_page, go_back, drag:
  Interaction tools that return an ``InteractionResult`` with a page_view.
- ask_about_screenshot: Capture the current page and answer a prompt about it.
- ground_elements_by_text: Locate UI elements via vision model (use descriptive prompts
  with spatial context, colors, and element types for best accuracy).
- execute_javascript: Execute arbitrary JavaScript for advanced scenarios (use sparingly;
  prefer structured tools like click, fill_field for reliability).
- close_browser: Cleanly close the persistent Playwright browser.
"""

from .core import Browser, close_browser, get_browser
from .core.exceptions import BrowserToolError
from .core.page_view import PageView
from .interactions import (
    InteractionResult,
    click,
    drag,
    fill_field,
    go_back,
    press_keys,
    scroll_page,
)
from .javascript import JavaScriptResult, execute_javascript
from .page import open_url
from .select import select_option
from .snapshot_tool import view_page
from .vision import GroundingResult, ask_about_screenshot, ground_elements_by_text

__all__ = [
    "Browser",
    "BrowserToolError",
    "GroundingResult",
    "InteractionResult",
    "JavaScriptResult",
    "PageView",
    "ask_about_screenshot",
    "click",
    "close_browser",
    "drag",
    "execute_javascript",
    "fill_field",
    "get_browser",
    "go_back",
    "ground_elements_by_text",
    "open_url",
    "press_keys",
    "scroll_page",
    "select_option",
    "view_page",
]
