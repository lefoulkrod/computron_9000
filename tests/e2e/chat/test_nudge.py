"""E2E tests for nudge routing.

Verifies that the nudge bar sends the correct agent_id to /api/nudge
and that success/error toasts appear.
"""

import json

import pytest
from playwright.sync_api import Page, Route, expect

from tests.e2e.pages import ChatView, NetworkView


def _build_jsonl(events: list[dict]) -> str:
    return "".join(json.dumps(e) + "\n" for e in events)


def _event(payload_type, agent_id="root", agent_name="computron",
           depth=0, **payload_fields):
    payload = {"type": payload_type, **payload_fields}
    if payload_type in ("agent_started", "agent_completed"):
        payload.setdefault("agent_id", agent_id)
        payload.setdefault("agent_name", agent_name)
    return {
        "payload": payload,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "timestamp": "2026-05-10T00:00:00",
        "depth": depth,
    }


MULTI_AGENT_EVENTS = _build_jsonl([
    _event("agent_started", agent_id="root", agent_name="computron",
           parent_agent_id=None),
    _event("content", content="Delegating."),
    _event("agent_started", agent_id="sub1", agent_name="research_agent",
           parent_agent_id="root", depth=1),
    _event("content", agent_id="sub1", agent_name="research_agent",
           depth=1, content="On it."),
    _event("agent_completed", agent_id="sub1", agent_name="research_agent",
           depth=1, status="success"),
    _event("content", content="Done."),
    _event("agent_completed", agent_id="root", agent_name="computron",
           status="success"),
    _event("turn_end"),
])


@pytest.mark.e2e
def test_nudge_sends_correct_agent_id(page: Page):
    """Nudge bar sends the selected agent's ID to /api/nudge."""
    chat = ChatView(page).goto().new_conversation()
    page.route("**/api/chat", lambda route: route.fulfill(
        status=200,
        headers={"Content-Type": "application/json"},
        body=MULTI_AGENT_EVENTS,
    ))
    chat.send("test")
    chat.wait_streaming()
    page.wait_for_timeout(200)

    # Open network view, select the sub-agent
    network = NetworkView(page)
    expect(network.indicator).to_be_visible(timeout=5000)
    network.open()
    expect(network.agent_cards.first).to_be_visible(timeout=5000)
    activity = network.select_agent(1)
    expect(activity.root).to_be_visible(timeout=5000)

    # Intercept /api/nudge to capture the request body
    captured = []

    def capture_nudge(route: Route):
        body = json.loads(route.request.post_data)
        captured.append(body)
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"ok": True}),
        )

    page.route("**/api/nudge", capture_nudge)

    # Type into the nudge bar and send
    nudge_input = page.locator("input[placeholder*='Send a nudge']")
    expect(nudge_input).to_be_visible(timeout=3000)
    nudge_input.fill("hey focus on the API")
    nudge_input.press("Enter")
    page.wait_for_timeout(500)

    assert len(captured) == 1, f"Expected 1 nudge request, got {len(captured)}"
    assert captured[0]["agent_id"] == "sub1"
    assert captured[0]["message"] == "hey focus on the API"

    # Success toast should appear
    toast_region = page.locator("[role='region'][aria-label='Notifications']")
    expect(toast_region).to_contain_text("Nudge sent", timeout=3000)


@pytest.mark.e2e
def test_nudge_shows_error_toast_on_409(page: Page):
    """Nudge bar shows a warning toast when the agent is no longer running."""
    chat = ChatView(page).goto().new_conversation()
    page.route("**/api/chat", lambda route: route.fulfill(
        status=200,
        headers={"Content-Type": "application/json"},
        body=MULTI_AGENT_EVENTS,
    ))
    chat.send("test")
    chat.wait_streaming()
    page.wait_for_timeout(200)

    network = NetworkView(page)
    expect(network.indicator).to_be_visible(timeout=5000)
    network.open()
    expect(network.agent_cards.first).to_be_visible(timeout=5000)
    activity = network.select_agent(1)
    expect(activity.root).to_be_visible(timeout=5000)

    # Mock /api/nudge to return 409
    page.route("**/api/nudge", lambda route: route.fulfill(
        status=409,
        headers={"Content-Type": "application/json"},
        body=json.dumps({"error": "No active turn for this conversation."}),
    ))

    nudge_input = page.locator("input[placeholder*='Send a nudge']")
    nudge_input.fill("hello")
    nudge_input.press("Enter")

    toast_region = page.locator("[role='region'][aria-label='Notifications']")
    expect(toast_region).to_contain_text("no longer running", timeout=3000)
