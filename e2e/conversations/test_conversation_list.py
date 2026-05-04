"""E2E tests for the conversations flyout panel.

Verifies creating, listing, switching between, and deleting conversations.
One test uses a real LLM response; the rest seed conversations directly
in the container for speed and determinism.
"""

import json
import time

from playwright.sync_api import Page, expect

from e2e._helpers import container_exec
from e2e.pages import ChatView
from e2e.pages.conversations_flyout import ConversationsFlyout

LLM_TIMEOUT = 180_000
CONV_DIR = "/var/lib/computron/conversations"


def _seed_conversation(
    conv_id: str,
    messages: list[dict],
    *,
    title: str = "",
) -> str:
    """Create a conversation on disk inside the container."""
    msgs_json = json.dumps(messages)
    script = (
        "import json, pathlib\n"
        f"d = pathlib.Path('{CONV_DIR}/{conv_id}')\n"
        "d.mkdir(parents=True, exist_ok=True)\n"
        f"(d / 'history.json').write_text({msgs_json!r})\n"
    )
    if title:
        meta = json.dumps({"title": title})
        script += f"(d / 'metadata.json').write_text({meta!r})\n"
    script += f"print('{conv_id}')\n"
    return container_exec(script)


def _delete_conversation(conv_id: str) -> None:
    """Remove a seeded conversation from the container."""
    container_exec(
        "import shutil, pathlib\n"
        f"p = pathlib.Path('{CONV_DIR}/{conv_id}')\n"
        "if p.exists(): shutil.rmtree(p)\n"
    )


def test_flyout_opens_and_closes(page: Page):
    """The flyout can be toggled open and closed."""
    ChatView(page).goto()
    flyout = ConversationsFlyout(page)

    flyout.open()
    flyout_panel = page.locator("[class*='flyout']")
    expect(flyout_panel.first).to_be_visible(timeout=5000)

    flyout.close()
    page.wait_for_timeout(500)
    expect(flyout_panel.first).not_to_be_visible()


def test_conversation_appears_after_real_message(page: Page):
    """A real LLM conversation shows up in the flyout with correct metadata."""
    chat = ChatView(page).goto().new_conversation()
    chat.send("reply with just the word yes").wait_streaming(timeout=LLM_TIMEOUT)

    flyout = ConversationsFlyout(page).open()
    expect(flyout.items.first).to_be_visible(timeout=5000)

    top = flyout.item(0)
    expect(top.description).to_contain_text("1 turn")
    expect(top.resume_button).to_be_visible()
    expect(top.delete_button).to_be_visible()


def test_multiple_conversations_listed_in_recency_order(page: Page):
    """Seeded conversations appear in most-recent-first order."""
    nonce = time.time_ns()
    ids = [f"e2e_order_{i}_{nonce}" for i in range(3)]
    titles = [f"Conv {chr(65 + i)} {nonce}" for i in range(3)]

    for i, (cid, title) in enumerate(zip(ids, titles)):
        _seed_conversation(cid, [
            {"role": "user", "content": f"msg {i}"},
            {"role": "assistant", "content": f"reply {i}"},
        ], title=title)
        time.sleep(0.2)

    try:
        ChatView(page).goto()
        flyout = ConversationsFlyout(page).open()
        expect(flyout.items.first).to_be_visible(timeout=5000)

        assert flyout.items.count() >= 3

        # Most recent (last seeded) should be first in the list
        name_locators = page.locator("[class*='item'] [class*='name']")
        top_three = [name_locators.nth(i).text_content() for i in range(3)]

        assert titles[2] in top_three[0], (
            f"Most recent conv should be first, got: {top_three}"
        )
        assert titles[1] in top_three[1], (
            f"Middle conv should be second, got: {top_three}"
        )
        assert titles[0] in top_three[2], (
            f"Oldest conv should be third, got: {top_three}"
        )
    finally:
        for cid in ids:
            _delete_conversation(cid)


def test_conversation_shows_correct_turn_count(page: Page):
    """Turn count reflects the number of user messages."""
    nonce = time.time_ns()
    one_turn_id = f"e2e_1turn_{nonce}"
    three_turn_id = f"e2e_3turn_{nonce}"

    _seed_conversation(one_turn_id, [
        {"role": "user", "content": "only question"},
        {"role": "assistant", "content": "only answer"},
    ], title=f"OneTurn {nonce}")

    time.sleep(0.2)

    _seed_conversation(three_turn_id, [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "q3"},
        {"role": "assistant", "content": "a3"},
    ], title=f"ThreeTurns {nonce}")

    try:
        ChatView(page).goto()
        flyout = ConversationsFlyout(page).open()
        expect(flyout.items.first).to_be_visible(timeout=5000)

        # 3-turn conv is most recent (seeded last) → item(0)
        top = flyout.item(0)
        expect(top.description).to_contain_text("3 turns")

        # 1-turn conv is older → item(1)
        second = flyout.item(1)
        expect(second.description).to_contain_text("1 turn")
    finally:
        _delete_conversation(one_turn_id)
        _delete_conversation(three_turn_id)


def test_switch_between_conversations(page: Page):
    """Resuming a conversation loads its messages into the chat view."""
    nonce = time.time_ns()
    older_id = f"e2e_switch_old_{nonce}"
    newer_id = f"e2e_switch_new_{nonce}"

    _seed_conversation(older_id, [
        {"role": "user", "content": f"ALPHA_MARKER_{nonce}"},
        {"role": "assistant", "content": "I see alpha."},
    ], title=f"Alpha Conv {nonce}")

    time.sleep(0.2)

    _seed_conversation(newer_id, [
        {"role": "user", "content": f"BETA_MARKER_{nonce}"},
        {"role": "assistant", "content": "I see beta."},
    ], title=f"Beta Conv {nonce}")

    try:
        ChatView(page).goto()
        flyout = ConversationsFlyout(page).open()
        expect(flyout.items.first).to_be_visible(timeout=5000)

        # Resume the newer conversation (item 0)
        flyout.item(0).resume()
        flyout.close()

        user_msgs = page.get_by_test_id("message-user")
        expect(user_msgs.first).to_contain_text(
            f"BETA_MARKER_{nonce}", timeout=10_000
        )

        assistant_msgs = page.get_by_test_id("message-assistant")
        expect(assistant_msgs.first).to_contain_text("I see beta.")

        # Switch to the older conversation (item 1)
        flyout.open()
        flyout.item(1).resume()
        flyout.close()

        expect(user_msgs.first).to_contain_text(
            f"ALPHA_MARKER_{nonce}", timeout=10_000
        )
        expect(assistant_msgs.first).to_contain_text("I see alpha.")
    finally:
        _delete_conversation(older_id)
        _delete_conversation(newer_id)


def test_delete_conversation(page: Page):
    """Deleting a conversation removes it from the list by identity."""
    nonce = time.time_ns()
    keep_id = f"e2e_keep_{nonce}"
    delete_id = f"e2e_delete_{nonce}"
    keep_title = f"KeepMe {nonce}"
    delete_title = f"DeleteMe {nonce}"

    _seed_conversation(keep_id, [
        {"role": "user", "content": "I should survive"},
        {"role": "assistant", "content": "Noted."},
    ], title=keep_title)

    time.sleep(0.2)

    _seed_conversation(delete_id, [
        {"role": "user", "content": "I will be deleted"},
        {"role": "assistant", "content": "Goodbye."},
    ], title=delete_title)

    try:
        ChatView(page).goto()
        flyout = ConversationsFlyout(page).open()
        expect(flyout.items.first).to_be_visible(timeout=5000)

        # Verify both are visible
        expect(page.get_by_text(delete_title)).to_be_visible()
        expect(page.get_by_text(keep_title)).to_be_visible()

        # Delete the most recent one (item 0 = delete_title)
        flyout.item(0).delete()
        page.wait_for_timeout(1000)

        # Deleted conversation is gone; kept one remains
        expect(page.get_by_text(delete_title)).not_to_be_visible()
        expect(page.get_by_text(keep_title)).to_be_visible()
    finally:
        _delete_conversation(keep_id)
        _delete_conversation(delete_id)
