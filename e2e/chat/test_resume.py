"""E2E tests for resuming a prior conversation.

Verifies that conversations persist across "New conversation" and reload
from the Conversations flyout with the full message history reconstructed
from history.json — user messages, assistant content, and tool-call
markers, in chronological order.
"""

import time

import pytest
from playwright.sync_api import expect

from e2e.pages import ChatView, ConversationsFlyout

LLM_TIMEOUT = 180_000


@pytest.fixture(scope="module")
def resumed(browser, browser_context_args):
    """Build a two-turn conversation, switch away, then resume it.

    Turn 1: user message with cw1 + assistant `run_bash_cmd` tool call.
    Turn 2: user message with cw2 + assistant plain-content echo reply.

    Yields a dict with the page handle and both codewords.
    """
    context = browser.new_context(**browser_context_args)
    page = context.new_page()
    nonce = time.time_ns()
    cw1 = f"ZULU-{nonce}"
    cw2 = f"ALPHA-{nonce}"

    chat = ChatView(page).goto().new_conversation()
    chat.send(f'run echo "{cw1}" in bash').wait_streaming(timeout=LLM_TIMEOUT)
    chat.send(f"now just reply with the single word: {cw2}").wait_streaming(
        timeout=LLM_TIMEOUT,
    )

    # Sanity: confirm the live render produced what we'll later expect to
    # come back. If this fails, the rest of the suite is meaningless.
    assert page.get_by_text(cw1).count() >= 1, "cw1 missing before switch"
    assert page.get_by_text("run_bash_cmd").count() >= 1, "tool call badge missing before switch"
    assert page.get_by_text(cw2).count() >= 1, "cw2 missing before switch"

    # Switch to a fresh conversation; previous markers should leave the DOM.
    chat.new_conversation()
    expect(page.get_by_text(cw1)).to_have_count(0)
    expect(page.get_by_text(cw2)).to_have_count(0)
    expect(page.get_by_text("run_bash_cmd")).to_have_count(0)

    # Resume the prior conversation. Topmost row = most recent
    # (sorted by started_at in conversations/_store.py).
    flyout = ConversationsFlyout(page).open()
    flyout.resume_top()
    flyout.close()  # so per-test assertions can't false-match list rows

    # Wait until at least one restored marker is visible before yielding.
    expect(page.get_by_text(cw1).first).to_be_visible(timeout=10_000)

    yield {"page": page, "cw1": cw1, "cw2": cw2}

    page.close()
    context.close()


# ── Turn 1 — assistant message with content + tool_call entries ─────


def test_turn_one_user_message_restored(resumed):
    """Turn 1's user message reappears with its codeword."""
    expect(resumed["page"].get_by_text(resumed["cw1"]).first).to_be_visible()


def test_turn_one_tool_call_badge_restored(resumed):
    """Turn 1's assistant tool_call entry renders as a ToolCallBlock badge."""
    expect(resumed["page"].get_by_text("run_bash_cmd").first).to_be_visible()


# ── Turn 2 — assistant message with content-only entries ────────────


def test_turn_two_user_message_restored(resumed):
    """Turn 2's user message reappears with its codeword."""
    expect(resumed["page"].get_by_text(resumed["cw2"]).first).to_be_visible()


def test_turn_two_assistant_content_restored(resumed):
    """Turn 2's assistant plain-content reply is restored alongside the user msg.

    The codeword appears in both the user message and the assistant's echo —
    count >= 2 proves the assistant content entry rendered, not just the
    user message. This is the only test that exercises the
    content-only assistant message shape (no tool_calls field).
    """
    page = resumed["page"]
    cw2 = resumed["cw2"]
    count = page.get_by_text(cw2).count()
    assert count >= 2, (
        f"Expected codeword in both user msg and assistant reply, got {count}"
    )
