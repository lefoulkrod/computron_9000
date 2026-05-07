"""POM for the inline file preview controls inside the Preview Panel."""

from __future__ import annotations

from playwright.sync_api import Locator, Page


class FilePreview:
    """Controls inside an active file tab: source/preview toggle, download, fullscreen."""

    def __init__(self, page: Page):
        self.page = page

    @property
    def content(self) -> Locator:
        return self.page.get_by_test_id("preview-content")

    @property
    def toggle(self) -> Locator:
        return self.content.get_by_test_id("file-view-toggle")

    @property
    def source_only(self) -> Locator:
        return self.content.get_by_test_id("file-view-source-only")

    def view_source(self) -> "FilePreview":
        self.page.get_by_test_id("file-view-source").click()
        self.page.wait_for_timeout(200)
        return self

    def view_preview(self) -> "FilePreview":
        self.page.get_by_test_id("file-view-preview").click()
        self.page.wait_for_timeout(200)
        return self

    def open_fullscreen(self) -> "FullscreenPreview":
        from .fullscreen_preview import FullscreenPreview

        self.page.get_by_test_id("file-fullscreen").click()
        self.page.wait_for_timeout(300)
        return FullscreenPreview(self.page)

    def download_button(self) -> Locator:
        return self.page.get_by_test_id("file-download")
