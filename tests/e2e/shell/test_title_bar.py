"""E2E tests for the chat title bar (replaces the old app header)."""

from playwright.sync_api import Page, expect

from tests.e2e.pages import ChatView

LLM_TIMEOUT = 180_000


def test_title_bar_is_present(page: Page):
    """The chat view shows a title bar with a title."""
    ChatView(page).goto()
    expect(page.get_by_test_id("chat-title-bar")).to_be_visible()
    expect(page.get_by_test_id("chat-title")).to_be_visible()


def test_turn_count_appears_after_a_turn(page: Page):
    """The title bar shows a turn count once the conversation has a turn."""
    chat = ChatView(page).goto().new_conversation()

    # No turns yet — the count is hidden.
    expect(page.get_by_test_id("chat-turns")).to_have_count(0)

    chat.send('say "hello" and nothing else').wait_streaming(timeout=LLM_TIMEOUT)

    expect(page.get_by_test_id("chat-turns")).to_be_visible()
    expect(page.get_by_test_id("chat-turns")).to_contain_text("1 turn")
