"""POM for the tabbed Preview Panel shared by Chat and Agent Activity views."""

from __future__ import annotations

from playwright.sync_api import Locator, Page

from .file_preview import FilePreview


class PreviewPanel:
    """Tabbed preview panel on the right side of the UI."""

    def __init__(self, page: Page):
        self.page = page
        self.file = FilePreview(page)

    @property
    def root(self) -> Locator:
        return self.page.get_by_test_id("preview-panel")

    @property
    def split_handle(self) -> Locator:
        return self.page.locator("[role='separator']")

    @property
    def tab_bar(self) -> Locator:
        return self.page.get_by_test_id("preview-tab-bar")

    @property
    def tabs(self) -> Locator:
        return self.tab_bar.locator("button")

    @property
    def terminal_tab(self) -> Locator:
        return self.page.get_by_test_id("preview-tab-terminal")

    @property
    def browser_tab(self) -> Locator:
        return self.page.get_by_test_id("preview-tab-browser")

    @property
    def file_tabs(self) -> Locator:
        """All file tabs across the panel."""
        return self.page.locator("[data-testid^='preview-tab-file:']")

    def file_tab(self, filename: str) -> Locator:
        return self.page.locator(f"[data-testid='preview-tab-file:{filename}']")

    @property
    def content(self) -> Locator:
        return self.page.get_by_test_id("preview-content")

    def select_tab(self, tab: Locator) -> "PreviewPanel":
        tab.click()
        self.page.wait_for_timeout(200)
        return self

    def close_first_tab(self) -> "PreviewPanel":
        self.tabs.first.locator("[class*='tabClose']").click()
        self.page.wait_for_timeout(200)
        return self

    def close_all_tabs(self) -> "PreviewPanel":
        while self.tabs.count() > 0:
            self.close_first_tab()
        return self

    def open_file_tab_by_extension(self, ext: str) -> str | None:
        """Click the first file tab whose name ends with ext. Returns filename or None."""
        tabs = self.file_tabs
        for i in range(tabs.count()):
            testid = tabs.nth(i).get_attribute("data-testid") or ""
            filename = testid.replace("preview-tab-file:", "")
            if filename.endswith(ext):
                tabs.nth(i).click()
                self.page.wait_for_timeout(200)
                return filename
        return None
