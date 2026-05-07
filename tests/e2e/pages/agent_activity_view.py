"""POM for the Agent Activity view — a single sub-agent's activity stream."""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import Locator, Page

from .preview_panel import PreviewPanel

if TYPE_CHECKING:
    from .network_view import NetworkView


class AgentActivityView:
    """Single agent's activity log. Shares the preview panel with Chat View."""

    def __init__(self, page: Page):
        self.page = page
        self.preview = PreviewPanel(page)

    @property
    def root(self) -> Locator:
        return self.page.get_by_test_id("agent-activity-view")

    @property
    def file_preview_btns(self) -> Locator:
        """Preview buttons on file outputs inside this agent's activity stream."""
        return self.page.get_by_test_id("file-preview-btn")

    def open_first_file_preview(self) -> AgentActivityView:
        btn = self.file_preview_btns.first
        btn.scroll_into_view_if_needed()
        btn.click(force=True)
        self.page.wait_for_timeout(300)
        return self

    def back_to_network(self) -> NetworkView:
        from .network_view import NetworkView as _NetworkView

        self.page.get_by_test_id("back-btn-agents").click()
        self.page.wait_for_timeout(500)
        return _NetworkView(self.page)
