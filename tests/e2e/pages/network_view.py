"""POM for the full-width Network View showing the agent graph."""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import Locator, Page

if TYPE_CHECKING:
    from .agent_activity_view import AgentActivityView


class AgentCard:
    """A single agent card in the network graph."""

    def __init__(self, locator: Locator):
        self._loc = locator

    @property
    def name(self) -> str:
        return self._loc.locator("[class*='name']").text_content() or ""

    @property
    def status_dot(self) -> Locator:
        return self._loc.locator("[class*='dot']")

    @property
    def sub_agent_badge(self) -> Locator:
        return self._loc.locator("[class*='agents']")

    @property
    def tool_badge(self) -> Locator:
        return self._loc.locator("[class*='iter']")

    @property
    def time_badge(self) -> Locator:
        return self._loc.locator("[class*='time']")

    def is_complete(self) -> bool:
        cls = self.status_dot.get_attribute("class") or ""
        return "complete" in cls

    def click(self) -> None:
        self._loc.click()


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

    def card(self, index: int) -> AgentCard:
        return AgentCard(self.agent_cards.nth(index))

    def card_by_name(self, name: str) -> AgentCard:
        """Find a card by its displayed agent name (case-insensitive contains)."""
        for i in range(self.agent_cards.count()):
            card = AgentCard(self.agent_cards.nth(i))
            if name.lower() in card.name.lower():
                return card
        raise ValueError(f"No card found with name containing '{name}'")

    def select_agent(self, index: int) -> AgentActivityView:
        from .agent_activity_view import AgentActivityView as _AgentActivityView

        self.agent_cards.nth(index).click()
        self.page.wait_for_timeout(500)
        return _AgentActivityView(self.page)

    def back_to_chat(self) -> None:
        self.page.get_by_test_id("back-btn-chat").click()
        self.page.wait_for_timeout(500)
