"""E2E test for agent card status dot colors.

Verifies that agent cards display the correct status dot classes for
success, error, and running states.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from playwright.sync_api import Page, Route, expect

from e2e.pages import ChatView, NetworkView


def _build_jsonl(events: list[dict]) -> str:
    return "".join(json.dumps(e) + "\n" for e in events)


# ── Mock with mixed success/error outcomes ───────────────────────────────

MIXED_STATUS_EVENTS = _build_jsonl([
    {
        "payload": {
            "type": "agent_started",
            "agent_id": "root",
            "agent_name": "computron",
            "parent_agent_id": None,
        },
        "agent_id": "root",
        "agent_name": "computron",
        "timestamp": "2026-05-03T10:00:00",
        "depth": 0,
    },
    {
        "payload": {
            "type": "agent_started",
            "agent_id": "ok_agent",
            "agent_name": "successful_agent",
            "parent_agent_id": "root",
        },
        "agent_id": "ok_agent",
        "agent_name": "successful_agent",
        "timestamp": "2026-05-03T10:00:01",
        "depth": 1,
    },
    {
        "payload": {
            "type": "agent_started",
            "agent_id": "fail_agent",
            "agent_name": "failing_agent",
            "parent_agent_id": "root",
        },
        "agent_id": "fail_agent",
        "agent_name": "failing_agent",
        "timestamp": "2026-05-03T10:00:02",
        "depth": 1,
    },
    {
        "payload": {"type": "content", "content": "Success."},
        "agent_id": "ok_agent",
        "agent_name": "successful_agent",
        "timestamp": "2026-05-03T10:00:03",
        "depth": 1,
    },
    {
        "payload": {"type": "content", "content": "About to fail."},
        "agent_id": "fail_agent",
        "agent_name": "failing_agent",
        "timestamp": "2026-05-03T10:00:04",
        "depth": 1,
    },
    {
        "payload": {
            "type": "agent_completed",
            "agent_id": "ok_agent",
            "agent_name": "successful_agent",
            "status": "success",
        },
        "agent_id": "ok_agent",
        "agent_name": "successful_agent",
        "timestamp": "2026-05-03T10:00:05",
        "depth": 1,
    },
    {
        "payload": {
            "type": "agent_completed",
            "agent_id": "fail_agent",
            "agent_name": "failing_agent",
            "status": "error",
        },
        "agent_id": "fail_agent",
        "agent_name": "failing_agent",
        "timestamp": "2026-05-03T10:00:06",
        "depth": 1,
    },
    {
        "payload": {"type": "content", "content": "One failed."},
        "agent_id": "root",
        "agent_name": "computron",
        "timestamp": "2026-05-03T10:00:07",
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
        "timestamp": "2026-05-03T10:00:08",
        "depth": 0,
    },
    {
        "payload": {"type": "turn_end"},
        "agent_id": "root",
        "timestamp": "2026-05-03T10:00:09",
        "depth": 0,
    },
])


# ── Mock with agents still running (no turn_end) ────────────────────────
# Uses a streaming HTTP server so Playwright's fetch stays open, keeping
# the stop button visible and agents in "running" state.

RUNNING_EVENTS = _build_jsonl([
    {
        "payload": {
            "type": "agent_started",
            "agent_id": "root",
            "agent_name": "computron",
            "parent_agent_id": None,
        },
        "agent_id": "root",
        "agent_name": "computron",
        "timestamp": "2026-05-03T10:00:00",
        "depth": 0,
    },
    {
        "payload": {
            "type": "agent_started",
            "agent_id": "working",
            "agent_name": "working_agent",
            "parent_agent_id": "root",
        },
        "agent_id": "working",
        "agent_name": "working_agent",
        "timestamp": "2026-05-03T10:00:01",
        "depth": 1,
    },
    {
        "payload": {"type": "content", "content": "Working..."},
        "agent_id": "working",
        "agent_name": "working_agent",
        "timestamp": "2026-05-03T10:00:02",
        "depth": 1,
    },
])


class _StreamingHandler(BaseHTTPRequestHandler):
    """Streams RUNNING_EVENTS then blocks until the test signals done."""

    complete_event = threading.Event()

    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        self.wfile.write(RUNNING_EVENTS.encode())
        self.wfile.flush()
        # Hold connection open so frontend stays in streaming state
        self.complete_event.wait(timeout=30)
        # Send completion events
        finish = _build_jsonl([
            {
                "payload": {
                    "type": "agent_completed",
                    "agent_id": "working",
                    "agent_name": "working_agent",
                    "status": "success",
                },
                "agent_id": "working",
                "timestamp": "2026-05-03T10:00:10",
                "depth": 1,
            },
            {
                "payload": {
                    "type": "agent_completed",
                    "agent_id": "root",
                    "agent_name": "computron",
                    "status": "success",
                },
                "agent_id": "root",
                "timestamp": "2026-05-03T10:00:11",
                "depth": 0,
            },
            {
                "payload": {"type": "turn_end"},
                "agent_id": "root",
                "timestamp": "2026-05-03T10:00:12",
                "depth": 0,
            },
        ])
        self.wfile.write(finish.encode())
        self.wfile.flush()

    def log_message(self, *args):
        pass


@pytest.fixture
def streaming_server():
    """Start a local HTTP server that streams events with a pause."""
    _StreamingHandler.complete_event.clear()
    server = HTTPServer(("127.0.0.1", 9199), _StreamingHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    yield server
    _StreamingHandler.complete_event.set()
    server.shutdown()


# ── Tests ────────────────────────────────────────────────────────────────


def test_error_agent_shows_error_dot(page: Page):
    """A failed agent card displays the 'error' status dot."""
    chat = ChatView(page).goto().new_conversation()

    def mock(route: Route):
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=MIXED_STATUS_EVENTS,
        )

    page.route("**/api/chat", mock)
    chat.send("test")
    chat.wait_streaming()

    network = NetworkView(page)
    network.open()
    expect(network.agent_cards.first).to_be_visible(timeout=5000)

    fail_card = network.card_by_name("Failing Agent")
    dot = fail_card.status_dot
    dot_class = dot.get_attribute("class") or ""
    assert "error" in dot_class, f"Expected 'error' in class, got: {dot_class}"


def test_success_agent_shows_complete_dot(page: Page):
    """A successful agent card displays the 'complete' status dot."""
    chat = ChatView(page).goto().new_conversation()

    def mock(route: Route):
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=MIXED_STATUS_EVENTS,
        )

    page.route("**/api/chat", mock)
    chat.send("test")
    chat.wait_streaming()

    network = NetworkView(page)
    network.open()
    expect(network.agent_cards.first).to_be_visible(timeout=5000)

    ok_card = network.card_by_name("Successful Agent")
    dot = ok_card.status_dot
    dot_class = dot.get_attribute("class") or ""
    assert "complete" in dot_class, f"Expected 'complete' in class, got: {dot_class}"


def test_running_agent_shows_running_dot(page: Page, streaming_server):
    """An in-progress agent card shows the 'running' (pulsing) status dot."""
    chat = ChatView(page).goto().new_conversation()

    # Route /api/chat to our streaming server that holds the connection open
    def route_to_server(route: Route):
        route.continue_(url="http://127.0.0.1:9199/api/chat")

    page.route("**/api/chat", route_to_server)
    chat.send("test")

    # Don't wait_streaming — the stream is intentionally held open.
    # Wait for the network indicator to appear (sub-agent spawned).
    network = NetworkView(page)
    expect(network.indicator).to_be_visible(timeout=10_000)

    network.open()
    expect(network.agent_cards.first).to_be_visible(timeout=5000)

    working_card = network.card_by_name("Working Agent")
    dot = working_card.status_dot
    dot_class = dot.get_attribute("class") or ""
    assert "running" in dot_class, f"Expected 'running' in class, got: {dot_class}"

    # Signal the server to finish, let the stream complete
    _StreamingHandler.complete_event.set()
    chat.wait_streaming()

    # After completion, dot should transition to 'complete'
    page.wait_for_timeout(500)
    dot_class = dot.get_attribute("class") or ""
    assert "complete" in dot_class, f"Expected 'complete' after finish, got: {dot_class}"
