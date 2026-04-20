"""POM for the Conversations sidebar flyout panel."""

from __future__ import annotations

from playwright.sync_api import Locator, Page


class ConversationsFlyout:
    """Sidebar flyout listing prior conversations with resume/delete actions."""

    def __init__(self, page: Page):
        self.page = page

    @property
    def sidebar_button(self) -> Locator:
        return self.page.get_by_role("button", name="Conversations")

    @property
    def resume_buttons(self) -> Locator:
        return self.page.locator("[title='Resume this conversation']")

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
