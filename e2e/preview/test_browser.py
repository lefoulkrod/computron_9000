"""E2E test for the agent's browser tool.

Asks the agent to navigate to example.com and asserts the browser
preview tab renders — proving Chrome successfully launched under the
computron user (regression guard for the entrypoint chown bug). The
assistant's reply text is intentionally not checked; this is an infra
test, not a model-quality test.
"""

from playwright.sync_api import Page, expect

from e2e.pages import ChatView

LLM_TIMEOUT = 180_000


def test_browser_snapshot_appears(page: Page):
    """Browsing produces a browser preview tab — Chrome launched successfully."""
    chat = ChatView(page).goto().new_conversation()
    chat.send("browse to https://example.com").wait_streaming(timeout=LLM_TIMEOUT)
    expect(chat.preview.browser_tab).to_be_visible(timeout=10_000)
