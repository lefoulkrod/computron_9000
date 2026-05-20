"""POM for the left navigation sidebar — collapse/expand + nav."""

from __future__ import annotations

from playwright.sync_api import Locator, Page


class Sidebar:
    """The collapsible left rail: brand, New chat, nav, footer."""

    def __init__(self, page: Page):
        self.page = page

    @property
    def root(self) -> Locator:
        return self.page.get_by_test_id("sidebar")

    @property
    def toggle(self) -> Locator:
        return self.page.get_by_test_id("sidebar-toggle")

    @property
    def new_chat(self) -> Locator:
        return self.page.get_by_test_id("sidebar-new-chat")

    def is_collapsed(self) -> bool:
        return self.root.get_attribute("data-collapsed") == "true"

    def set_collapsed(self, collapsed: bool) -> "Sidebar":
        if self.is_collapsed() != collapsed:
            self.toggle.click()
            self.page.wait_for_timeout(250)
        return self
