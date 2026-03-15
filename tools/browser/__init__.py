"""Browser tools package.

Important: the browser used by these tools is long-lived within the process
and maintains browser state between tool calls. This includes cookies,
localStorage/sessionStorage, open pages/tabs, and other session-specific
state. Call ``close_browser`` (or restart the process) to fully reset the
browser and clear that state when needed.

Public API:
- open_url: Navigate to a URL and return a PageView.
- browse_page: Browse the current page (no navigation) with ``[role] name``
  markers for interactive elements.  Optional ``scope`` parameter to focus
  on a specific section.
- read_page: Read the current page as clean markdown text for reading
  articles, documentation, or search results.
- click, fill_field, press_keys, select_option, scroll_page, go_back, drag:
  Interaction tools that return a formatted page view string.
- inspect_page: Visually inspect the current page and answer a question about it.
- perform_visual_action: Ask a vision model to decide and execute the next GUI
  action (click, type, scroll, drag, etc.).
- execute_javascript: Execute arbitrary JavaScript for advanced scenarios (use sparingly;
  prefer structured tools like click, fill_field for reliability).
- close_browser: Cleanly close the persistent Playwright browser.
"""

from .core import Browser, close_browser, get_browser
from .core.exceptions import BrowserToolError
from .core.page_view import PageView
from .interactions import (
    click,
    drag,
    fill_field,
    go_back,
    press_and_hold,
    press_keys,
    scroll_page,
)
from .javascript import execute_javascript
from .page import open_url
from .read_content import read_page
from .save_content import save_page_content
from .select import select_option
from .snapshot_tool import browse_page
from .vision import (
    inspect_page,
    perform_visual_action,
)

__all__ = [
    "Browser",
    "BrowserToolError",
    "PageView",
    "browse_page",
    "click",
    "close_browser",
    "drag",
    "execute_javascript",
    "fill_field",
    "get_browser",
    "go_back",
    "inspect_page",
    "open_url",
    "perform_visual_action",
    "press_and_hold",
    "press_keys",
    "read_page",
    "save_page_content",
    "scroll_page",
    "select_option",
]
