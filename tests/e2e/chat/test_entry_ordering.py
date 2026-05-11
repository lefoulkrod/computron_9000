"""E2E tests for activity log entry ordering.

Verifies that thinking, content, and tool_call entries appear in
chronological order in both the chat view and the agent activity view.

The original bug: tool_call events dispatched to the React reducer
synchronously while thinking/content tokens were deferred to a
requestAnimationFrame callback. Even when events arrive in one batch,
the dispatch timing caused tool calls to appear before their preceding
thinking blocks. The fix unifies all activity log entries into a single
RAF-flushed buffer.
"""

import json

import pytest
from playwright.sync_api import Page, Route, expect

from tests.e2e.pages import ChatView, NetworkView


def _build_jsonl(events: list[dict]) -> str:
    return "".join(json.dumps(e) + "\n" for e in events)


def _event(payload_type, agent_id="root", agent_name="computron",
           depth=0, **payload_fields):
    """Build a single JSONL event dict.

    Lifecycle events (agent_started, agent_completed) need agent_id and
    agent_name inside the payload because the frontend reads them from
    there when registering agents in the state tree.
    """
    payload = {"type": payload_type, **payload_fields}
    if payload_type in ("agent_started", "agent_completed"):
        payload.setdefault("agent_id", agent_id)
        payload.setdefault("agent_name", agent_name)
    return {
        "payload": payload,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "timestamp": "2026-05-09T00:00:00",
        "depth": depth,
    }


# Root agent: thinking → content → tool_call → thinking → content
SINGLE_AGENT_EVENTS = _build_jsonl([
    _event("agent_started", agent_id="root", agent_name="computron",
           parent_agent_id=None),
    _event("content", thinking="Planning the approach"),
    _event("content", content="Here is my plan."),
    _event("tool_call", name="run_bash_cmd"),
    _event("content", thinking="Reviewing the output"),
    _event("content", content="Done."),
    _event("agent_completed", agent_id="root", agent_name="computron",
           status="success"),
    _event("turn_end"),
])


# Root + sub-agent. Sub-agent: thinking → content → tool_call → content
MULTI_AGENT_EVENTS = _build_jsonl([
    _event("agent_started", agent_id="root", agent_name="computron",
           parent_agent_id=None),
    _event("content", content="Spawning a helper."),
    _event("agent_started", agent_id="sub1", agent_name="helper_agent",
           parent_agent_id="root", depth=1),
    _event("content", agent_id="sub1", agent_name="helper_agent",
           depth=1, thinking="Let me figure this out"),
    _event("content", agent_id="sub1", agent_name="helper_agent",
           depth=1, content="Working on it."),
    _event("tool_call", agent_id="sub1", agent_name="helper_agent",
           depth=1, name="write_file"),
    _event("content", agent_id="sub1", agent_name="helper_agent",
           depth=1, content="File written."),
    _event("agent_completed", agent_id="sub1", agent_name="helper_agent",
           depth=1, status="success"),
    _event("content", content="Helper finished."),
    _event("agent_completed", agent_id="root", agent_name="computron",
           status="success"),
    _event("turn_end"),
])


def _mock_chat_with(body: str):
    def handler(route: Route):
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=body,
        )
    return handler


def _get_entries(container):
    """Return ordered (type, text) tuples for all activity entries."""
    entries = container.locator(
        "[data-testid='entry-thinking'],"
        "[data-testid='entry-content'],"
        "[data-testid='entry-tool-call']"
    )
    count = entries.count()
    result = []
    for i in range(count):
        el = entries.nth(i)
        tid = el.get_attribute("data-testid")
        text = el.inner_text().strip()
        result.append((tid, text))
    return result


# ── Chat view ──────────────────────────────────────────────────────────


@pytest.mark.e2e
def test_chat_view_entry_order(page: Page):
    """Thinking → content → tool_call → thinking → content in the chat view."""
    chat = ChatView(page).goto().new_conversation()
    page.route("**/api/chat", _mock_chat_with(SINGLE_AGENT_EVENTS))
    chat.send("test")
    chat.wait_streaming()
    page.wait_for_timeout(500)

    msg = page.get_by_test_id("message-assistant").last
    expect(msg).to_be_visible(timeout=5000)

    entries = _get_entries(msg)
    types = [t for t, _ in entries]
    assert types == [
        "entry-thinking",
        "entry-content",
        "entry-tool-call",
        "entry-thinking",
        "entry-content",
    ], f"Chat view entries out of order: {types}"

    assert "Planning the approach" in entries[0][1]
    assert "Here is my plan." in entries[1][1]
    assert "run_bash_cmd" in entries[2][1]
    assert "Reviewing the output" in entries[3][1]
    assert "Done." in entries[4][1]


# ── Activity view ──────────────────────────────────────────────────────


@pytest.mark.e2e
def test_activity_view_entry_order(page: Page):
    """Sub-agent activity view shows thinking → content → tool_call → content."""
    chat = ChatView(page).goto().new_conversation()
    page.route("**/api/chat", _mock_chat_with(MULTI_AGENT_EVENTS))
    chat.send("test")
    chat.wait_streaming()
    page.wait_for_timeout(200)

    network = NetworkView(page)
    expect(network.indicator).to_be_visible(timeout=5000)
    network.open()
    expect(network.agent_cards.first).to_be_visible(timeout=5000)

    # Drill into the sub-agent
    activity = network.select_agent(1)
    expect(activity.root).to_be_visible(timeout=5000)

    entries = _get_entries(activity.root)
    types = [t for t, _ in entries]
    assert types == [
        "entry-thinking",
        "entry-content",
        "entry-tool-call",
        "entry-content",
    ], f"Activity view entries out of order: {types}"

    assert "Let me figure this out" in entries[0][1]
    assert "Working on it." in entries[1][1]
    assert "write_file" in entries[2][1]
    assert "File written." in entries[3][1]
