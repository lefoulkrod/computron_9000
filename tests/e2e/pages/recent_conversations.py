"""POM for the inline recent-conversations list in the sidebar."""

from __future__ import annotations

from playwright.sync_api import Locator, Page


class RecentConversationItem:
    """A single row in the recent-conversations list."""

    def __init__(self, locator: Locator):
        self._loc = locator

    @property
    def title(self) -> str:
        return self._loc.locator("[class*='itemTitle']").text_content() or ""

    def open(self) -> None:
        """Click the row to load that conversation into the chat view."""
        self._loc.click()

    def delete(self) -> None:
        """Reveal and click the row's delete button."""
        self._loc.hover()
        self._loc.get_by_test_id("recent-delete").click()


class RecentConversations:
    """The sidebar's inline recent-conversations list — search + day groups.

    Always visible while the sidebar is expanded (the default); there is
    no open/close, unlike the old flyout.
    """

    def __init__(self, page: Page):
        self.page = page

    @property
    def root(self) -> Locator:
        return self.page.get_by_test_id("recent-conversations")

    @property
    def items(self) -> Locator:
        return self.page.get_by_test_id("recent-item")

    @property
    def search(self) -> Locator:
        return self.page.get_by_test_id("recent-search")

    def item(self, index: int) -> RecentConversationItem:
        return RecentConversationItem(self.items.nth(index))

    def open_top(self) -> "RecentConversations":
        """Load the most recent conversation."""
        self.items.first.click()
        return self
