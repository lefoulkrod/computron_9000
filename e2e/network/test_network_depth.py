"""E2E test for deeply nested agent trees (3 levels).

Verifies the network view correctly renders a root → sub-agent →
sub-sub-agent hierarchy with proper parent-child relationships.
"""

import json

from playwright.sync_api import Page, Route, expect

from e2e.pages import ChatView, NetworkView


def _build_jsonl(events: list[dict]) -> str:
    return "".join(json.dumps(e) + "\n" for e in events)


DEEP_TREE_EVENTS = _build_jsonl([
    # Level 0: root
    {
        "payload": {
            "type": "agent_started",
            "agent_id": "root",
            "agent_name": "computron",
            "parent_agent_id": None,
            "instruction": "Orchestrate a complex task",
        },
        "agent_id": "root",
        "agent_name": "computron",
        "timestamp": "2026-05-03T10:00:00",
        "depth": 0,
    },
    # Level 1: planner (child of root)
    {
        "payload": {
            "type": "agent_started",
            "agent_id": "planner",
            "agent_name": "planner_agent",
            "parent_agent_id": "root",
            "instruction": "Plan the approach",
        },
        "agent_id": "planner",
        "agent_name": "planner_agent",
        "timestamp": "2026-05-03T10:00:01",
        "depth": 1,
    },
    # Level 2: executor (child of planner)
    {
        "payload": {
            "type": "agent_started",
            "agent_id": "executor",
            "agent_name": "executor_agent",
            "parent_agent_id": "planner",
            "instruction": "Execute step 1",
        },
        "agent_id": "executor",
        "agent_name": "executor_agent",
        "timestamp": "2026-05-03T10:00:02",
        "depth": 2,
    },
    # Level 2: reviewer (child of planner)
    {
        "payload": {
            "type": "agent_started",
            "agent_id": "reviewer",
            "agent_name": "reviewer_agent",
            "parent_agent_id": "planner",
            "instruction": "Review the output",
        },
        "agent_id": "reviewer",
        "agent_name": "reviewer_agent",
        "timestamp": "2026-05-03T10:00:03",
        "depth": 2,
    },
    # Content for leaf agents
    {
        "payload": {"type": "content", "content": "Executed step 1."},
        "agent_id": "executor",
        "agent_name": "executor_agent",
        "timestamp": "2026-05-03T10:00:04",
        "depth": 2,
    },
    {
        "payload": {"type": "tool_call", "name": "bash"},
        "agent_id": "executor",
        "agent_name": "executor_agent",
        "timestamp": "2026-05-03T10:00:05",
        "depth": 2,
    },
    {
        "payload": {"type": "content", "content": "Looks good."},
        "agent_id": "reviewer",
        "agent_name": "reviewer_agent",
        "timestamp": "2026-05-03T10:00:06",
        "depth": 2,
    },
    # Complete leaf agents
    {
        "payload": {
            "type": "agent_completed",
            "agent_id": "executor",
            "agent_name": "executor_agent",
            "status": "success",
        },
        "agent_id": "executor",
        "agent_name": "executor_agent",
        "timestamp": "2026-05-03T10:00:07",
        "depth": 2,
    },
    {
        "payload": {
            "type": "agent_completed",
            "agent_id": "reviewer",
            "agent_name": "reviewer_agent",
            "status": "success",
        },
        "agent_id": "reviewer",
        "agent_name": "reviewer_agent",
        "timestamp": "2026-05-03T10:00:08",
        "depth": 2,
    },
    # Complete planner
    {
        "payload": {"type": "content", "content": "Plan executed."},
        "agent_id": "planner",
        "agent_name": "planner_agent",
        "timestamp": "2026-05-03T10:00:09",
        "depth": 1,
    },
    {
        "payload": {
            "type": "agent_completed",
            "agent_id": "planner",
            "agent_name": "planner_agent",
            "status": "success",
        },
        "agent_id": "planner",
        "agent_name": "planner_agent",
        "timestamp": "2026-05-03T10:00:10",
        "depth": 1,
    },
    # Complete root
    {
        "payload": {"type": "content", "content": "All done."},
        "agent_id": "root",
        "agent_name": "computron",
        "timestamp": "2026-05-03T10:00:11",
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
        "timestamp": "2026-05-03T10:00:12",
        "depth": 0,
    },
    {
        "payload": {"type": "turn_end"},
        "agent_id": "root",
        "timestamp": "2026-05-03T10:00:13",
        "depth": 0,
    },
])


def _mock_chat(route: Route):
    route.fulfill(
        status=200,
        headers={"Content-Type": "application/json"},
        body=DEEP_TREE_EVENTS,
    )


def test_three_level_tree_renders_all_cards(page: Page):
    """A 3-level deep tree shows all 4 agent cards."""
    chat = ChatView(page).goto().new_conversation()
    page.route("**/api/chat", _mock_chat)

    chat.send("test")
    chat.wait_streaming()

    network = NetworkView(page)
    expect(network.indicator).to_be_visible(timeout=5000)
    expect(network.indicator).to_contain_text("4 agents")

    network.open()
    expect(network.agent_cards.first).to_be_visible(timeout=5000)
    assert network.agent_cards.count() == 4

    network.card_by_name("Computron")
    network.card_by_name("Planner Agent")
    network.card_by_name("Executor Agent")
    network.card_by_name("Reviewer Agent")


def test_mid_level_agent_shows_sub_agent_badge(page: Page):
    """Planner (level 1) shows '2 sub-agents' badge for its children."""
    chat = ChatView(page).goto().new_conversation()
    page.route("**/api/chat", _mock_chat)

    chat.send("test")
    chat.wait_streaming()

    network = NetworkView(page)
    network.open()
    expect(network.agent_cards.first).to_be_visible(timeout=5000)

    planner = network.card_by_name("Planner Agent")
    expect(planner.sub_agent_badge).to_contain_text("2 sub-agents")

    root = network.card_by_name("Computron")
    expect(root.sub_agent_badge).to_contain_text("1 sub-agent")


def test_leaf_agents_have_no_sub_agent_badge(page: Page):
    """Executor and Reviewer (level 2) have no sub-agent badges."""
    chat = ChatView(page).goto().new_conversation()
    page.route("**/api/chat", _mock_chat)

    chat.send("test")
    chat.wait_streaming()

    network = NetworkView(page)
    network.open()
    expect(network.agent_cards.first).to_be_visible(timeout=5000)

    executor = network.card_by_name("Executor Agent")
    reviewer = network.card_by_name("Reviewer Agent")
    expect(executor.sub_agent_badge).not_to_be_visible()
    expect(reviewer.sub_agent_badge).not_to_be_visible()


def test_drill_into_nested_agent_activity(page: Page):
    """Can navigate into a level-2 agent's activity view from the network."""
    chat = ChatView(page).goto().new_conversation()
    page.route("**/api/chat", _mock_chat)

    chat.send("test")
    chat.wait_streaming()

    network = NetworkView(page)
    network.open()
    expect(network.agent_cards.first).to_be_visible(timeout=5000)

    executor = network.card_by_name("Executor Agent")
    executor.click()
    page.wait_for_timeout(500)

    activity_view = page.get_by_test_id("agent-activity-view")
    expect(activity_view).to_be_visible(timeout=5000)
