"""POM for the fullscreen file preview overlay."""

from __future__ import annotations

from playwright.sync_api import Locator, Page


class FullscreenPreview:
    """Viewport-filling overlay for an open file."""

    def __init__(self, page: Page):
        self.page = page

    @property
    def root(self) -> Locator:
        return self.page.get_by_test_id("fullscreen-preview")

    def close_with_escape(self) -> None:
        self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(300)

    def back(self) -> None:
        self.page.get_by_test_id("fullscreen-back").click()
        self.page.wait_for_timeout(300)
