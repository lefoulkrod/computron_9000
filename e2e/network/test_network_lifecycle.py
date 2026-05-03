"""E2E test for agent network indicator and card basics.

Mocks the /api/chat JSONL stream to control agent spawning precisely,
then verifies core network indicator behavior, card metadata, and
navigation.
"""

import json

import pytest
from playwright.sync_api import Page, Route, expect

from e2e.pages import ChatView, NetworkView


def _build_jsonl(events: list[dict]) -> str:
    return "".join(json.dumps(e) + "\n" for e in events)


MOCK_EVENTS = _build_jsonl([
    {
        "payload": {
            "type": "agent_started",
            "agent_id": "root",
            "agent_name": "computron",
            "parent_agent_id": None,
            "instruction": "Do some research and write code",
        },
        "agent_id": "root",
        "agent_name": "computron",
        "timestamp": "2026-05-03T10:00:00",
        "depth": 0,
    },
    {
        "payload": {
            "type": "agent_started",
            "agent_id": "sub1",
            "agent_name": "research_agent",
            "parent_agent_id": "root",
            "instruction": "Research the topic",
        },
        "agent_id": "sub1",
        "agent_name": "research_agent",
        "timestamp": "2026-05-03T10:00:01",
        "depth": 1,
    },
    {
        "payload": {
            "type": "agent_started",
            "agent_id": "sub2",
            "agent_name": "code_expert",
            "parent_agent_id": "root",
            "instruction": "Write the implementation",
        },
        "agent_id": "sub2",
        "agent_name": "code_expert",
        "timestamp": "2026-05-03T10:00:02",
        "depth": 1,
    },
    {
        "payload": {"type": "content", "content": "Research complete."},
        "agent_id": "sub1",
        "agent_name": "research_agent",
        "timestamp": "2026-05-03T10:00:03",
        "depth": 1,
    },
    {
        "payload": {"type": "tool_call", "name": "bash"},
        "agent_id": "sub2",
        "agent_name": "code_expert",
        "timestamp": "2026-05-03T10:00:04",
        "depth": 1,
    },
    {
        "payload": {"type": "tool_call", "name": "write_file"},
        "agent_id": "sub2",
        "agent_name": "code_expert",
        "timestamp": "2026-05-03T10:00:05",
        "depth": 1,
    },
    {
        "payload": {"type": "content", "content": "Code written."},
        "agent_id": "sub2",
        "agent_name": "code_expert",
        "timestamp": "2026-05-03T10:00:06",
        "depth": 1,
    },
    {
        "payload": {
            "type": "agent_completed",
            "agent_id": "sub1",
            "agent_name": "research_agent",
            "status": "success",
        },
        "agent_id": "sub1",
        "agent_name": "research_agent",
        "timestamp": "2026-05-03T10:00:07",
        "depth": 1,
    },
    {
        "payload": {
            "type": "agent_completed",
            "agent_id": "sub2",
            "agent_name": "code_expert",
            "status": "success",
        },
        "agent_id": "sub2",
        "agent_name": "code_expert",
        "timestamp": "2026-05-03T10:00:08",
        "depth": 1,
    },
    {
        "payload": {"type": "content", "content": "Both tasks done."},
        "agent_id": "root",
        "agent_name": "computron",
        "timestamp": "2026-05-03T10:00:09",
        "depth": 0,
    },
    {
        "payload": {
            "type": "agent_completed",
            "agent_id": "root",
            "agent_name": "computron",
            "status": "success",
        },
        "agent_id": "root",
        "agent_name": "computron",
        "timestamp": "2026-05-03T10:00:10",
        "depth": 0,
    },
    {
        "payload": {"type": "turn_end"},
        "agent_id": "root",
        "agent_name": "computron",
        "timestamp": "2026-05-03T10:00:11",
        "depth": 0,
    },
])


def _mock_chat(route: Route):
    route.fulfill(
        status=200,
        headers={"Content-Type": "application/json"},
        body=MOCK_EVENTS,
    )


@pytest.fixture
def network_after_turn(page: Page):
    """Send a mocked multi-agent turn and return the NetworkView."""
    chat = ChatView(page).goto().new_conversation()
    page.route("**/api/chat", _mock_chat)
    chat.send("test")
    chat.wait_streaming()
    network = NetworkView(page)
    expect(network.indicator).to_be_visible(timeout=5000)
    return network


# ── Indicator ────────────────────────────────────────────────────────────


def test_indicator_shows_agent_count(page: Page, network_after_turn):
    """Indicator badge shows total agent count."""
    expect(network_after_turn.indicator).to_contain_text("3 agents")


def test_indicator_complete_status(page: Page, network_after_turn):
    """Indicator dot shows 'complete' when all agents finish."""
    dot = network_after_turn.indicator.locator("[class*='complete']")
    expect(dot).to_be_visible()


def test_indicator_clears_on_new_conversation(page: Page, network_after_turn):
    """Starting a new conversation removes the indicator."""
    page.unroute("**/api/chat")
    ChatView(page).new_conversation()
    expect(network_after_turn.indicator).not_to_be_visible()


# ── Cards ────────────────────────────────────────────────────────────────


def test_cards_render_with_correct_names(page: Page, network_after_turn):
    """Network view shows cards with correct agent names."""
    network_after_turn.open()
    expect(network_after_turn.agent_cards.first).to_be_visible(timeout=5000)
    assert network_after_turn.agent_cards.count() == 3

    network_after_turn.card_by_name("Computron")
    network_after_turn.card_by_name("Research Agent")
    network_after_turn.card_by_name("Code Expert")


def test_root_card_sub_agent_badge(page: Page, network_after_turn):
    """Root card shows '2 sub-agents' badge."""
    network_after_turn.open()
    expect(network_after_turn.agent_cards.first).to_be_visible(timeout=5000)

    root = network_after_turn.card_by_name("Computron")
    expect(root.sub_agent_badge).to_contain_text("2 sub-agents")


def test_sub_agent_tool_badge(page: Page, network_after_turn):
    """Code Expert card shows '2 tools' badge."""
    network_after_turn.open()
    expect(network_after_turn.agent_cards.first).to_be_visible(timeout=5000)

    code_expert = network_after_turn.card_by_name("Code Expert")
    expect(code_expert.tool_badge).to_contain_text("2 tools")


def test_agent_without_tools_no_badge(page: Page, network_after_turn):
    """Research Agent has no tool badge."""
    network_after_turn.open()
    expect(network_after_turn.agent_cards.first).to_be_visible(timeout=5000)

    research = network_after_turn.card_by_name("Research Agent")
    expect(research.tool_badge).not_to_be_visible()


def test_leaf_agents_no_sub_agent_badge(page: Page, network_after_turn):
    """Leaf agents don't show sub-agent badges."""
    network_after_turn.open()
    expect(network_after_turn.agent_cards.first).to_be_visible(timeout=5000)

    research = network_after_turn.card_by_name("Research Agent")
    code_expert = network_after_turn.card_by_name("Code Expert")
    expect(research.sub_agent_badge).not_to_be_visible()
    expect(code_expert.sub_agent_badge).not_to_be_visible()


def test_cards_show_elapsed_time(page: Page, network_after_turn):
    """All cards display an elapsed time badge."""
    network_after_turn.open()
    expect(network_after_turn.agent_cards.first).to_be_visible(timeout=5000)

    for i in range(network_after_turn.agent_cards.count()):
        card = network_after_turn.card(i)
        expect(card.time_badge).to_be_visible()


# ── Navigation ───────────────────────────────────────────────────────────


def test_click_card_opens_activity_view(page: Page, network_after_turn):
    """Clicking a sub-agent card navigates to its activity view."""
    network_after_turn.open()
    expect(network_after_turn.agent_cards.first).to_be_visible(timeout=5000)

    activity = network_after_turn.select_agent(1)
    expect(activity.root).to_be_visible(timeout=5000)
