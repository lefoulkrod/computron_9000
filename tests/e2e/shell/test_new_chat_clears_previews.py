"""E2E test: starting a new chat clears the previous conversation's previews.

Regression: opening a new conversation used to leave the previous
conversation's preview tabs (browser, files, terminal) visible in the
preview panel. The fix dispatches AGENT_STATE RESET + preview.reset()
on the new-chat path.
"""

import base64
import json

import pytest
from playwright.sync_api import Page, Route, expect

from tests.e2e.pages import ChatView, PreviewPanel, Sidebar


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
        "timestamp": "2026-05-09T00:00:00",
        "depth": depth,
    }


_HTML_BYTES = b"<html><body>hello</body></html>"
_HTML_B64 = base64.b64encode(_HTML_BYTES).decode()

# Root agent emits a previewable file output, then content, then ends.
_FILE_OUTPUT_EVENTS = _build_jsonl([
    _event("agent_started", agent_id="root", agent_name="computron",
           parent_agent_id=None),
    _event("file_output", filename="report.html",
           content_type="text/html", content=_HTML_B64,
           path="/tmp/report.html"),
    _event("content", content="Wrote report.html."),
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


@pytest.mark.e2e
def test_new_chat_clears_open_preview_tabs(page: Page):
    chat = ChatView(page).goto().new_conversation()
    page.route("**/api/chat", _mock_chat_with(_FILE_OUTPUT_EVENTS))
    chat.send("write a report")
    chat.wait_streaming(timeout=10_000)

    # Open the file as a preview tab.
    preview_btn = page.get_by_test_id("file-preview-btn").first
    expect(preview_btn).to_be_visible(timeout=5_000)
    preview_btn.click()

    panel = PreviewPanel(page)
    expect(panel.file_tab("report.html")).to_be_visible(timeout=5_000)

    # Click "New chat" — preview panel should be empty afterward.
    Sidebar(page).new_chat.click()
    page.wait_for_timeout(500)

    expect(panel.file_tabs).to_have_count(0)
    expect(panel.root).to_have_count(0)
