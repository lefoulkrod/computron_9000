"""Core browser components for web-browsing tools.

Public API:
- _Browser: minimal persistent Playwright browser core
"""

from .browser import Browser, close_browser, get_browser

__all__ = ["Browser", "close_browser", "get_browser"]
