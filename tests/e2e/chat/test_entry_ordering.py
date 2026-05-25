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


# Root agent emits one spawn_agent tool call → one sub-agent runs and
# finishes → root replies. Used to verify the chat footer counts the
# spawn_agent call and the panel surfaces it.
SPAWN_ONLY_EVENTS = _build_jsonl([
    _event("agent_started", agent_id="root", agent_name="computron",
           parent_agent_id=None),
    _event("tool_call", name="spawn_agent",
           arguments={"agent_name": "worker"}),
    _event("spawn_requested", correlation_id="c-1"),
    _event("agent_started", agent_id="sub1", agent_name="worker",
           parent_agent_id="root", correlation_id="c-1", depth=1,
           instruction="Do the work"),
    _event("agent_completed", agent_id="sub1", agent_name="worker",
           depth=1, status="success"),
    _event("content", content="Worker finished."),
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
    """Return ordered (type, text) tuples for all activity entries.

    Completed thinking blocks auto-collapse to a 'Show thinking' toggle;
    expand them first so the inner text is readable for assertions.
    """
    selector = (
        "[data-testid='entry-thinking'],"
        "[data-testid='entry-content'],"
        "[data-testid='entry-tool-call']"
    )
    entries = container.locator(selector)
    count = entries.count()
    for i in range(count):
        el = entries.nth(i)
        if el.get_attribute("data-testid") == "entry-thinking":
            toggle = el.get_by_test_id("thinking-toggle")
            if toggle.count() > 0 and "Show thinking" in (toggle.inner_text() or ""):
                toggle.click()
    result = []
    for i in range(count):
        el = entries.nth(i)
        tid = el.get_attribute("data-testid")
        text = el.inner_text().strip()
        result.append((tid, text))
    return result


# ── Chat view ──────────────────────────────────────────────────────────


@pytest.mark.e2e
def test_chat_view_hides_thinking_and_tool_calls(page: Page):
    """Chat view shows only content inline; thinking and tool_calls are
    hidden and surfaced via the per-turn activity footer."""
    chat = ChatView(page).goto().new_conversation()
    page.route("**/api/chat", _mock_chat_with(SINGLE_AGENT_EVENTS))
    chat.send("test")
    chat.wait_streaming()
    page.wait_for_timeout(500)

    msg = page.get_by_test_id("message-assistant").last
    expect(msg).to_be_visible(timeout=5000)

    # Only content entries render inline — no thinking, no raw tool_call.
    expect(msg.get_by_test_id("entry-thinking")).to_have_count(0)
    expect(msg.get_by_test_id("entry-tool-call")).to_have_count(0)
    contents = msg.get_by_test_id("entry-content")
    expect(contents).to_have_count(2)
    expect(contents.nth(0)).to_contain_text("Here is my plan.")
    expect(contents.nth(1)).to_contain_text("Done.")


@pytest.mark.e2e
def test_chat_view_activity_footer_reveals_hidden(page: Page):
    """The activity footer summarises the hidden thinking + tool calls
    and reveals them in a panel on click."""
    chat = ChatView(page).goto().new_conversation()
    page.route("**/api/chat", _mock_chat_with(SINGLE_AGENT_EVENTS))
    chat.send("test")
    chat.wait_streaming()
    page.wait_for_timeout(500)

    msg = page.get_by_test_id("message-assistant").last
    expect(msg).to_be_visible(timeout=5000)

    toggle = msg.get_by_test_id("activity-toggle")
    expect(toggle).to_be_visible()
    expect(toggle).to_contain_text("1 tool")
    expect(toggle).to_contain_text("2 thoughts")

    expect(msg.get_by_test_id("activity-panel")).to_have_count(0)
    toggle.click()

    panel = msg.get_by_test_id("activity-panel")
    expect(panel).to_be_visible()
    expect(panel).to_contain_text("Planning the approach")
    expect(panel).to_contain_text("Reviewing the output")
    expect(panel).to_contain_text("run_bash_cmd")

    # Toggling again hides the panel
    toggle.click()
    expect(msg.get_by_test_id("activity-panel")).to_have_count(0)


@pytest.mark.e2e
def test_chat_footer_counts_spawn_agent_calls(page: Page):
    """spawn_agent tool calls land in the activity log like any other tool
    call. The footer count and the expanded panel both include them.

    Regression: the streaming path used to filter spawn_agent out of the
    activity log (because the SpawnCard already showed the action), which
    made the chat footer report 0 tools on a spawn-only turn.
    """
    chat = ChatView(page).goto().new_conversation()
    page.route("**/api/chat", _mock_chat_with(SPAWN_ONLY_EVENTS))
    chat.send("delegate this")
    chat.wait_streaming()
    page.wait_for_timeout(500)

    msg = page.get_by_test_id("message-assistant").last
    expect(msg).to_be_visible(timeout=5000)

    toggle = msg.get_by_test_id("activity-toggle")
    expect(toggle).to_be_visible()
    expect(toggle).to_contain_text("1 tool")

    toggle.click()
    panel = msg.get_by_test_id("activity-panel")
    expect(panel).to_be_visible()
    expect(panel).to_contain_text("spawn_agent")
    expect(panel).to_contain_text("worker")


# ── Activity view ──────────────────────────────────────────────────────


@pytest.mark.e2e
def test_activity_view_entry_order(page: Page):
    """Sub-agent activity view shows thinking → content → tool_call → content
    via the ActivityRail's per-type rows."""
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

    rows = activity.root.locator(
        "[data-testid='activity-row-thinking'],"
        "[data-testid='activity-row-content'],"
        "[data-testid='activity-row-tool']"
    )
    count = rows.count()
    types = []
    for i in range(count):
        tid = rows.nth(i).get_attribute("data-testid")
        types.append(tid)
    assert types == [
        "activity-row-thinking",
        "activity-row-content",
        "activity-row-tool",
        "activity-row-content",
    ], f"Activity view entries out of order: {types}"

    expect(rows.nth(0)).to_contain_text("Let me figure this out")
    expect(rows.nth(1)).to_contain_text("Working on it.")
    expect(rows.nth(2)).to_contain_text("write_file")
    expect(rows.nth(3)).to_contain_text("File written.")
