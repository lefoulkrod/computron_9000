"""E2E test for the spawn_agent grouped card in the chat stream.

Mocks the /api/chat JSONL stream so the root agent spawns two
sub-agents, then verifies the SpawnCard renders inline in the
assistant turn and that clicking a row drills into that agent's
activity view.
"""

import json

import pytest
from playwright.sync_api import Page, Route, expect

from tests.e2e.pages import ChatView


def _build_jsonl(events: list[dict]) -> str:
    return "".join(json.dumps(e) + "\n" for e in events)


def _event(payload: dict, agent_id: str, agent_name: str, ts: str, depth: int) -> dict:
    return {
        "payload": payload,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "timestamp": ts,
        "depth": depth,
    }


MOCK_EVENTS = _build_jsonl([
    _event(
        {"type": "agent_started", "agent_id": "root", "agent_name": "computron",
         "parent_agent_id": None, "instruction": "Delegate the work"},
        "root", "computron", "2026-05-03T10:00:00", 0,
    ),
    _event({"type": "spawn_requested", "correlation_id": "c-1"},
           "root", "computron", "2026-05-03T10:00:01", 0),
    _event({"type": "spawn_requested", "correlation_id": "c-2"},
           "root", "computron", "2026-05-03T10:00:01", 0),
    _event(
        {"type": "agent_started", "agent_id": "sub1", "agent_name": "research_agent",
         "parent_agent_id": "root", "instruction": "Research the topic",
         "correlation_id": "c-1"},
        "sub1", "research_agent", "2026-05-03T10:00:02", 1,
    ),
    _event(
        {"type": "agent_started", "agent_id": "sub2", "agent_name": "code_expert",
         "parent_agent_id": "root", "instruction": "Write the implementation",
         "correlation_id": "c-2"},
        "sub2", "code_expert", "2026-05-03T10:00:03", 1,
    ),
    _event({"type": "content", "content": "Research complete."}, "sub1",
           "research_agent", "2026-05-03T10:00:04", 1),
    _event({"type": "content", "content": "Code written."}, "sub2",
           "code_expert", "2026-05-03T10:00:05", 1),
    _event({"type": "agent_completed", "agent_id": "sub1",
            "agent_name": "research_agent", "status": "success"}, "sub1",
           "research_agent", "2026-05-03T10:00:06", 1),
    _event({"type": "agent_completed", "agent_id": "sub2",
            "agent_name": "code_expert", "status": "success"}, "sub2",
           "code_expert", "2026-05-03T10:00:07", 1),
    _event({"type": "content", "content": "Both tasks done."}, "root",
           "computron", "2026-05-03T10:00:08", 0),
    _event({"type": "agent_completed", "agent_id": "root",
            "agent_name": "computron", "status": "success"}, "root",
           "computron", "2026-05-03T10:00:09", 0),
    _event({"type": "turn_end"}, "root", "computron", "2026-05-03T10:00:10", 0),
])


def _mock_chat(route: Route):
    route.fulfill(
        status=200,
        headers={"Content-Type": "application/json"},
        body=MOCK_EVENTS,
    )


@pytest.fixture
def chat_after_spawn(page: Page) -> ChatView:
    """Send a mocked turn that spawns two sub-agents."""
    chat = ChatView(page).goto().new_conversation()
    page.route("**/api/chat", _mock_chat)
    chat.send("delegate this")
    chat.wait_streaming()
    expect(page.get_by_test_id("spawn-card")).to_be_visible(timeout=5000)
    return chat


def test_spawn_card_renders_in_chat(page: Page, chat_after_spawn):
    """The spawn card appears inline in the assistant turn."""
    card = page.get_by_test_id("spawn-card")
    expect(card).to_contain_text("spawn_agent")
    expect(card).to_contain_text("2 agents")


def test_spawn_card_has_a_row_per_agent(page: Page, chat_after_spawn):
    """One clickable row per spawned sub-agent."""
    rows = page.get_by_test_id("spawn-card-row")
    expect(rows).to_have_count(2)
    card = page.get_by_test_id("spawn-card")
    expect(card).to_contain_text("Research Agent")
    expect(card).to_contain_text("Code Expert")


def test_raw_spawn_tool_call_is_hidden(page: Page, chat_after_spawn):
    """The raw spawn_agent tool-call line is replaced by the card."""
    tool_calls = page.get_by_test_id("entry-tool-call")
    for i in range(tool_calls.count()):
        assert "spawn_agent" not in (tool_calls.nth(i).text_content() or "")


def test_click_row_opens_agent_activity_view(page: Page, chat_after_spawn):
    """Clicking a spawn-card row drills into that agent's activity view."""
    page.get_by_test_id("spawn-card-row").first.click()
    page.wait_for_timeout(500)
    expect(page.get_by_test_id("agent-activity-view")).to_be_visible(timeout=5000)
