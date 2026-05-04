"""POM for the Conversations sidebar flyout panel."""

from __future__ import annotations

from playwright.sync_api import Locator, Page


class ConversationItem:
    """A single conversation entry in the flyout list."""

    def __init__(self, locator: Locator):
        self._loc = locator

    @property
    def title(self) -> str:
        return self._loc.locator("[class*='name']").text_content() or ""

    @property
    def description(self) -> Locator:
        return self._loc.locator("[class*='desc']")

    @property
    def resume_button(self) -> Locator:
        return self._loc.locator("[title='Resume this conversation']")

    @property
    def delete_button(self) -> Locator:
        return self._loc.locator("[title='Delete this conversation']")

    def resume(self) -> None:
        self.resume_button.click()

    def delete(self) -> None:
        self.delete_button.click()


class ConversationsFlyout:
    """Sidebar flyout listing prior conversations with resume/delete actions."""

    def __init__(self, page: Page):
        self.page = page

    @property
    def sidebar_button(self) -> Locator:
        return self.page.get_by_role("button", name="Conversations")

    @property
    def items(self) -> Locator:
        return self.page.locator("li[class*='item']")

    @property
    def resume_buttons(self) -> Locator:
        return self.page.locator("[title='Resume this conversation']")

    def item(self, index: int) -> ConversationItem:
        return ConversationItem(self.items.nth(index))

    def open(self) -> "ConversationsFlyout":
        self.sidebar_button.click()
        self.page.wait_for_timeout(500)
        return self

    def close(self) -> "ConversationsFlyout":
        self.sidebar_button.click()
        self.page.wait_for_timeout(500)
        return self

    def resume_top(self) -> "ConversationsFlyout":
        """Click the Resume button on the topmost (most recent) conversation."""
        self.resume_buttons.first.click()
        return self
