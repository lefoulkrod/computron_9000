"""E2E tests for multi-turn conversation state.

Verifies that preview state persists across turns, accumulates correctly,
and clears on new conversation.
"""

from playwright.sync_api import Page, expect

from e2e.pages import ChatView

LLM_TIMEOUT = 180_000


def test_terminal_persists_across_turns(page: Page):
    """Terminal output from turn 1 should still be visible in turn 2."""
    chat = ChatView(page).goto().new_conversation()

    # Turn 1
    chat.send('run echo "turn-one" in bash').wait_streaming(timeout=LLM_TIMEOUT)
    assert chat.preview.terminal_tab.is_visible(), (
        "Terminal tab should appear after turn 1"
    )

    # Turn 2
    chat.send('run echo "turn-two" in bash').wait_streaming(timeout=LLM_TIMEOUT)
    expect(chat.preview.terminal_tab).to_be_visible()

    chat.preview.select_tab(chat.preview.terminal_tab)
    text = chat.preview.content.text_content() or ""
    assert "turn-one" in text and "turn-two" in text, (
        f"Terminal should contain output from both turns, got: {text[:300]}"
    )


def test_file_tabs_persist_across_turns(page: Page):
    """File preview tabs from turn 1 should still be visible after turn 2."""
    chat = ChatView(page).goto().new_conversation()

    # Turn 1 — ask the agent to create a file
    chat.send(
        'create a simple text file called persist_test.txt '
        'with the content "hello" and send it to me'
    ).wait_streaming(timeout=LLM_TIMEOUT)

    assert chat.file_preview_btns.count() > 0, (
        "Agent should produce a file output with a Preview button"
    )
    chat.file_preview_btns.first.click()
    chat.preview.file_tabs.first.wait_for(state="visible", timeout=5_000)
    file_tab_count = chat.preview.file_tabs.count()

    # Turn 2 — send a follow-up that doesn't produce files
    chat.send('say "acknowledged"').wait_streaming(timeout=LLM_TIMEOUT)

    assert chat.preview.file_tabs.count() == file_tab_count, (
        f"File tabs should persist across turns, expected {file_tab_count} "
        f"but got {chat.preview.file_tabs.count()}"
    )


def test_new_conversation_clears_previews(page: Page):
    """Starting a new conversation should clear all preview tabs."""
    chat = ChatView(page).goto().new_conversation()

    chat.send('run echo "before-reset" in bash').wait_streaming(timeout=LLM_TIMEOUT)
    expect(chat.preview.root).to_be_visible()

    chat.new_conversation()

    expect(chat.preview.root).not_to_be_visible()
    expect(chat.preview.split_handle).not_to_be_visible()


def test_new_conversation_allows_fresh_previews(page: Page):
    """After clearing, new previews should appear from fresh messages."""
    chat = ChatView(page).goto().new_conversation()

    chat.send('run echo "old" in bash').wait_streaming(timeout=LLM_TIMEOUT)

    chat.new_conversation()

    chat.send('run echo "fresh" in bash').wait_streaming(timeout=LLM_TIMEOUT)

    if chat.preview.terminal_tab.is_visible():
        chat.preview.select_tab(chat.preview.terminal_tab)
        text = chat.preview.content.text_content() or ""
        assert "old" not in text, (
            f"New conversation terminal contains old content: {text[:300]}"
        )
