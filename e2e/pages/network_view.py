"""POM for the full-width Network View showing the agent graph."""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import Locator, Page

if TYPE_CHECKING:
    from .agent_activity_view import AgentActivityView


class NetworkView:
    """Agent network graph. Reached via the network indicator on the chat view."""

    def __init__(self, page: Page):
        self.page = page

    @property
    def indicator(self) -> Locator:
        """Network indicator badge in the chat header; visible once sub-agents exist."""
        return self.page.get_by_test_id("network-indicator")

    def open(self) -> NetworkView:
        self.indicator.click()
        self.page.wait_for_timeout(500)
        return self

    @property
    def agent_cards(self) -> Locator:
        return self.page.locator("[data-agent-id]")

    def select_agent(self, index: int) -> AgentActivityView:
        from .agent_activity_view import AgentActivityView as _AgentActivityView

        self.agent_cards.nth(index).click()
        self.page.wait_for_timeout(500)
        return _AgentActivityView(self.page)

    def back_to_chat(self) -> None:
        self.page.get_by_test_id("back-btn-chat").click()
        self.page.wait_for_timeout(500)
