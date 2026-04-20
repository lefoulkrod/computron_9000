"""POM for the Chat view — the default main view."""

from __future__ import annotations

from playwright.sync_api import Locator, Page

from .preview_panel import PreviewPanel

_DEFAULT_LLM_TIMEOUT = 180_000


class ChatView:
    """Main chat view: the multi-turn conversation with the root agent."""

    def __init__(self, page: Page):
        self.page = page
        self.preview = PreviewPanel(page)

    def goto(self) -> "ChatView":
        self.page.goto("/")
        return self

    def send(self, text: str) -> "ChatView":
        textarea = self.page.locator("textarea")
        textarea.fill(text)
        textarea.press("Enter")
        return self

    def wait_streaming(self, timeout: int = _DEFAULT_LLM_TIMEOUT) -> "ChatView":
        """Wait until the assistant finishes streaming (Stop button disappears)."""
        stop_btn = self.page.locator("button[title='Stop generation']")
        try:
            stop_btn.wait_for(state="visible", timeout=10_000)
        except Exception:
            pass
        stop_btn.wait_for(state="hidden", timeout=timeout)
        return self

    def new_conversation(self) -> "ChatView":
        self.page.locator("button[title='New conversation']").click()
        self.page.wait_for_timeout(500)
        return self

    def attach_file(self, path: str) -> "ChatView":
        """Attach a file to the next outgoing message via the hidden file input."""
        self.page.locator("#fileInput").set_input_files(path)
        self.page.wait_for_timeout(200)
        return self

    @property
    def file_preview_btns(self) -> Locator:
        """All 'Preview' buttons on file outputs in the chat stream."""
        return self.page.get_by_test_id("file-preview-btn")

    def open_all_file_previews(self) -> "ChatView":
        """Click every Preview button in the chat to open all files as tabs."""
        btns = self.file_preview_btns
        for i in range(btns.count()):
            btn = btns.nth(i)
            btn.scroll_into_view_if_needed()
            btn.click(force=True)
            self.page.wait_for_timeout(300)
        return self
