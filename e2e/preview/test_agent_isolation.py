"""E2E tests for per-agent preview isolation.

Spawns two sub-agents that each produce terminal output and file output
with distinct content, then verifies that selecting each agent in the
network view shows only that agent's previews.
"""

import pytest
from playwright.sync_api import Page, expect

from e2e.pages import AgentActivityView, ChatView, NetworkView

LLM_TIMEOUT = 300_000


@pytest.fixture(scope="module")
def isolation_page(browser, browser_context_args):
    """Spawn two sub-agents with distinct terminal + file outputs.

    Agent 1 (code_expert): runs echo "agent-one", creates one.txt, sends it.
    Agent 2 (code_expert): runs echo "agent-two", creates two.txt, sends it.

    Waits for completion, then yields the page for all tests.
    """
    context = browser.new_context(**browser_context_args)
    page = context.new_page()
    chat = ChatView(page).goto().new_conversation()

    chat.send(
        "to enable e2e testing of sub-agent isolation, spawn two sub-agents "
        "in parallel using profile code_expert:\n"
        '1) first agent: run echo "agent-one" in bash, then create a text '
        'file called one.txt containing "hello from agent one" and use '
        "send_file to send it\n"
        '2) second agent: run echo "agent-two" in bash, then create a text '
        'file called two.txt containing "hello from agent two" and use '
        "send_file to send it",
    ).wait_streaming(timeout=LLM_TIMEOUT)

    network = NetworkView(page)
    assert network.indicator.is_visible(), (
        "Network indicator not visible — sub-agents may not have been spawned"
    )

    yield page

    page.close()
    context.close()


# ── Sub-agent spawning ──────────────────────────────────────────────


def test_subagents_spawned(isolation_page: Page):
    """At least 2 sub-agents should appear in the network graph."""
    network = NetworkView(isolation_page).open()

    assert network.agent_cards.count() >= 3, (
        f"Expected at least 3 agent cards (root + 2 subs), got {network.agent_cards.count()}"
    )


# ── Agent 1 previews ───────────────────────────────────────────────


def test_agent_one_has_own_terminal(isolation_page: Page):
    """Selecting the first sub-agent shows its terminal output."""
    network = NetworkView(isolation_page)
    activity = network.select_agent(1)

    expect(activity.root).to_be_visible()

    assert activity.preview.terminal_tab.is_visible(), (
        "Agent 1 should have a terminal tab"
    )
    activity.preview.select_tab(activity.preview.terminal_tab)
    expect(activity.preview.content).to_be_visible()


def test_agent_one_has_own_file(isolation_page: Page):
    """First sub-agent's file preview should show agent 1's content only."""
    activity = AgentActivityView(isolation_page)
    activity.open_first_file_preview()

    expect(activity.preview.file_tabs.first).to_be_visible()
    activity.preview.select_tab(activity.preview.file_tabs.first)
    text = activity.preview.content.text_content() or ""
    assert "hello from agent one" in text, (
        f"Agent 1's file should contain its own content, got: {text[:300]}"
    )
    assert "hello from agent two" not in text, (
        f"Agent 1's file leaked agent 2's content: {text[:300]}"
    )


# ── Agent 2 previews ───────────────────────────────────────────────


def test_agent_two_has_own_terminal(isolation_page: Page):
    """Selecting the second sub-agent shows its own terminal output."""
    activity = AgentActivityView(isolation_page)
    network = activity.back_to_network()
    activity = network.select_agent(2)

    expect(activity.root).to_be_visible()

    assert activity.preview.terminal_tab.is_visible(), (
        "Agent 2 should have a terminal tab"
    )
    activity.preview.select_tab(activity.preview.terminal_tab)
    expect(activity.preview.content).to_be_visible()


def test_agent_two_has_own_file(isolation_page: Page):
    """Second sub-agent's file preview should show agent 2's content only."""
    activity = AgentActivityView(isolation_page)
    activity.open_first_file_preview()

    expect(activity.preview.file_tabs.first).to_be_visible()
    activity.preview.select_tab(activity.preview.file_tabs.first)
    text = activity.preview.content.text_content() or ""
    assert "hello from agent two" in text, (
        f"Agent 2's file should contain its own content, got: {text[:300]}"
    )
    assert "hello from agent one" not in text, (
        f"Agent 2's file leaked agent 1's content: {text[:300]}"
    )


# ── Root isolation ──────────────────────────────────────────────────


def test_root_previews_independent(isolation_page: Page):
    """Returning to chat shows root agent's previews, not sub-agent's."""
    activity = AgentActivityView(isolation_page)
    network = activity.back_to_network()
    network.back_to_chat()

    chat = ChatView(isolation_page)
    file_tabs = chat.preview.file_tabs
    for i in range(file_tabs.count()):
        tab_id = file_tabs.nth(i).get_attribute("data-testid") or ""
        assert "one.txt" not in tab_id and "two.txt" not in tab_id, (
            f"Root preview contains sub-agent file: {tab_id}"
        )
