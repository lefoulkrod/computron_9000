"""E2E test for agent network persistence across turns.

Verifies that agent cards from a previous turn persist in the network
view when a second turn spawns new agents.
"""

import json

from playwright.sync_api import Page, Route, expect

from e2e.pages import ChatView, NetworkView


def _build_jsonl(events: list[dict]) -> str:
    return "".join(json.dumps(e) + "\n" for e in events)


TURN_1_EVENTS = _build_jsonl([
    {
        "payload": {
            "type": "agent_started",
            "agent_id": "root1",
            "agent_name": "computron",
            "parent_agent_id": None,
        },
        "agent_id": "root1",
        "agent_name": "computron",
        "timestamp": "2026-05-03T10:00:00",
        "depth": 0,
    },
    {
        "payload": {
            "type": "agent_started",
            "agent_id": "t1_sub1",
            "agent_name": "research_agent",
            "parent_agent_id": "root1",
        },
        "agent_id": "t1_sub1",
        "agent_name": "research_agent",
        "timestamp": "2026-05-03T10:00:01",
        "depth": 1,
    },
    {
        "payload": {"type": "content", "content": "Done."},
        "agent_id": "t1_sub1",
        "agent_name": "research_agent",
        "timestamp": "2026-05-03T10:00:02",
        "depth": 1,
    },
    {
        "payload": {
            "type": "agent_completed",
            "agent_id": "t1_sub1",
            "agent_name": "research_agent",
            "status": "success",
        },
        "agent_id": "t1_sub1",
        "agent_name": "research_agent",
        "timestamp": "2026-05-03T10:00:03",
        "depth": 1,
    },
    {
        "payload": {"type": "content", "content": "Turn 1 complete."},
        "agent_id": "root1",
        "agent_name": "computron",
        "timestamp": "2026-05-03T10:00:04",
        "depth": 0,
    },
    {
        "payload": {
            "type": "agent_completed",
            "agent_id": "root1",
            "agent_name": "computron",
            "status": "success",
        },
        "agent_id": "root1",
        "agent_name": "computron",
        "timestamp": "2026-05-03T10:00:05",
        "depth": 0,
    },
    {
        "payload": {"type": "turn_end"},
        "agent_id": "root1",
        "timestamp": "2026-05-03T10:00:06",
        "depth": 0,
    },
])

TURN_2_EVENTS = _build_jsonl([
    {
        "payload": {
            "type": "agent_started",
            "agent_id": "root2",
            "agent_name": "computron",
            "parent_agent_id": None,
        },
        "agent_id": "root2",
        "agent_name": "computron",
        "timestamp": "2026-05-03T10:01:00",
        "depth": 0,
    },
    {
        "payload": {
            "type": "agent_started",
            "agent_id": "t2_sub1",
            "agent_name": "code_expert",
            "parent_agent_id": "root2",
        },
        "agent_id": "t2_sub1",
        "agent_name": "code_expert",
        "timestamp": "2026-05-03T10:01:01",
        "depth": 1,
    },
    {
        "payload": {
            "type": "agent_started",
            "agent_id": "t2_sub2",
            "agent_name": "creative_writer",
            "parent_agent_id": "root2",
        },
        "agent_id": "t2_sub2",
        "agent_name": "creative_writer",
        "timestamp": "2026-05-03T10:01:02",
        "depth": 1,
    },
    {
        "payload": {"type": "content", "content": "Code done."},
        "agent_id": "t2_sub1",
        "agent_name": "code_expert",
        "timestamp": "2026-05-03T10:01:03",
        "depth": 1,
    },
    {
        "payload": {"type": "content", "content": "Writing done."},
        "agent_id": "t2_sub2",
        "agent_name": "creative_writer",
        "timestamp": "2026-05-03T10:01:04",
        "depth": 1,
    },
    {
        "payload": {
            "type": "agent_completed",
            "agent_id": "t2_sub1",
            "agent_name": "code_expert",
            "status": "success",
        },
        "agent_id": "t2_sub1",
        "agent_name": "code_expert",
        "timestamp": "2026-05-03T10:01:05",
        "depth": 1,
    },
    {
        "payload": {
            "type": "agent_completed",
            "agent_id": "t2_sub2",
            "agent_name": "creative_writer",
            "status": "success",
        },
        "agent_id": "t2_sub2",
        "agent_name": "creative_writer",
        "timestamp": "2026-05-03T10:01:06",
        "depth": 1,
    },
    {
        "payload": {"type": "content", "content": "Turn 2 complete."},
        "agent_id": "root2",
        "agent_name": "computron",
        "timestamp": "2026-05-03T10:01:07",
        "depth": 0,
    },
    {
        "payload": {
            "type": "agent_completed",
            "agent_id": "root2",
            "agent_name": "computron",
            "status": "success",
        },
        "agent_id": "root2",
        "agent_name": "computron",
        "timestamp": "2026-05-03T10:01:08",
        "depth": 0,
    },
    {
        "payload": {"type": "turn_end"},
        "agent_id": "root2",
        "timestamp": "2026-05-03T10:01:09",
        "depth": 0,
    },
])


def test_cards_persist_across_turns(page: Page):
    """Cards from turn 1 remain visible after turn 2 adds new agents."""
    chat = ChatView(page).goto().new_conversation()
    turn = [1]

    def mock_chat(route: Route):
        body = TURN_1_EVENTS if turn[0] == 1 else TURN_2_EVENTS
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=body,
        )

    page.route("**/api/chat", mock_chat)

    # Turn 1: root + research_agent
    chat.send("turn 1")
    chat.wait_streaming()

    network = NetworkView(page)
    expect(network.indicator).to_be_visible(timeout=5000)
    expect(network.indicator).to_contain_text("2 agents")

    # Turn 2: root + code_expert + creative_writer
    turn[0] = 2
    chat.send("turn 2")
    chat.wait_streaming()

    # Both trees are visible: turn 1 tree (2 cards) + turn 2 tree (3 cards)
    expect(network.indicator).to_contain_text("5 agents")

    network.open()
    expect(network.agent_cards.first).to_be_visible(timeout=5000)
    assert network.agent_cards.count() == 5

    # Turn 1 cards still present
    network.card_by_name("Research Agent")

    # Turn 2 cards added
    network.card_by_name("Code Expert")
    network.card_by_name("Creative Writer")
