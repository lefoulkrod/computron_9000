"""E2E tests for chat-input file uploads.

The text-file test still runs end-to-end against the real model — the
agent's ability to quote back the codeword from a small text file is a
cheap, reliable signal that the upload pipeline works.

The image test does NOT depend on a vision model. It mocks the chat
endpoint so it can verify two deterministic things:
    1. The outgoing /api/chat request carries the image bytes encoded
       correctly (base64 + content_type + filename).
    2. The user bubble renders the uploaded image as a base64 data URL.
"""

import base64
import json
from pathlib import Path
import time

from playwright.sync_api import Page, Route, expect

from tests.e2e.pages import ChatView

LLM_TIMEOUT = 180_000

_FIXTURE_RED_SQUARE = Path(__file__).resolve().parent.parent / "fixtures" / "red_square.png"


def _minimal_chat_response() -> str:
    """JSONL response with just enough to let the UI finish streaming."""
    events = [
        {"payload": {"type": "agent_started", "agent_id": "root",
                     "agent_name": "computron", "parent_agent_id": None},
         "agent_id": "root", "agent_name": "computron",
         "timestamp": "2026-05-09T00:00:00", "depth": 0},
        {"payload": {"type": "content", "content": "ok"},
         "agent_id": "root", "agent_name": "computron",
         "timestamp": "2026-05-09T00:00:00", "depth": 0},
        {"payload": {"type": "agent_completed", "agent_id": "root",
                     "agent_name": "computron", "status": "success"},
         "agent_id": "root", "agent_name": "computron",
         "timestamp": "2026-05-09T00:00:00", "depth": 0},
        {"payload": {"type": "turn_end"},
         "agent_id": "root", "agent_name": "computron",
         "timestamp": "2026-05-09T00:00:00", "depth": 0},
    ]
    return "".join(json.dumps(e) + "\n" for e in events)


def test_text_file_upload_round_trip(page: Page, tmp_path):
    """Uploading a text file lets the agent quote its contents back."""
    codeword = f"UPLOADED-{time.time_ns()}"
    text_file = tmp_path / "secret.txt"
    text_file.write_text(f"the secret codeword is {codeword}\n")

    chat = ChatView(page).goto().new_conversation()
    chat.attach_file(str(text_file)).send(
        "what's the secret codeword in the file i just uploaded?",
    ).wait_streaming(timeout=LLM_TIMEOUT)

    # Assert the codeword appears in the latest assistant message bubble —
    # not just anywhere on the page. The user bubble shows only the filename,
    # but scoping to the assistant element rules out any other source.
    # `.first` on the inner locator: the agent often quotes the codeword
    # multiple times (e.g. once in narration, once in a quoted block).
    assistant = page.get_by_test_id("message-assistant").last
    expect(assistant.get_by_text(codeword).first).to_be_visible(timeout=5_000)


def test_image_upload_round_trip(page: Page):
    """An attached image is base64-encoded into the /api/chat request and
    rendered in the user bubble as a data URL.

    Does not exercise the vision model — that's a model-quality check,
    not an upload-pipeline check.
    """
    assert _FIXTURE_RED_SQUARE.exists(), f"missing fixture {_FIXTURE_RED_SQUARE}"
    expected_b64 = base64.b64encode(_FIXTURE_RED_SQUARE.read_bytes()).decode()

    captured: dict = {}

    def handler(route: Route) -> None:
        captured["body"] = route.request.post_data
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=_minimal_chat_response(),
        )

    page.route("**/api/chat", handler)

    chat = ChatView(page).goto().new_conversation()
    chat.attach_file(str(_FIXTURE_RED_SQUARE)).send("describe this image")
    chat.wait_streaming(timeout=10_000)

    # 1. Outgoing request carried the image bytes.
    body = json.loads(captured["body"])
    assert body.get("data"), f"expected data[] in request body, got: {body!r}"
    attachment = body["data"][0]
    assert attachment["content_type"] == "image/png", attachment
    assert attachment["filename"] == _FIXTURE_RED_SQUARE.name, attachment
    assert attachment["base64"] == expected_b64, (
        "uploaded base64 doesn't match the original file bytes"
    )

    # 2. User bubble renders the image as a base64 data URL.
    user_msg = page.get_by_test_id("message-user").last
    img = user_msg.locator("img[src^='data:image/']")
    expect(img).to_be_visible(timeout=5_000)
    src = img.get_attribute("src") or ""
    assert expected_b64 in src, (
        "user bubble image src doesn't contain the uploaded image bytes"
    )
