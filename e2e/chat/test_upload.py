"""E2E tests for chat-input file uploads.

Verifies the upload mechanic end-to-end: file selected via the paperclip
input → posted to the backend → made available to the agent → agent
responds with content derived from the uploaded data.

Both a text file and an image are exercised. Image case requires the
configured vision model to identify a solid red square.
"""

from pathlib import Path
import time

import pytest
from playwright.sync_api import Page, expect

from e2e.pages import ChatView

LLM_TIMEOUT = 180_000

_FIXTURE_RED_SQUARE = Path(__file__).resolve().parent.parent / "fixtures" / "red_square.png"


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
    """Uploading a solid-red image lets the vision model identify the color."""
    assert _FIXTURE_RED_SQUARE.exists(), f"missing fixture {_FIXTURE_RED_SQUARE}"

    chat = ChatView(page).goto().new_conversation()
    chat.attach_file(str(_FIXTURE_RED_SQUARE)).send(
        "what is the dominant color of the image i just uploaded? "
        "answer with just the single color word.",
    ).wait_streaming(timeout=LLM_TIMEOUT)

    # The user bubble should render the uploaded image as a base64 data URL.
    user_msg = page.get_by_test_id("message-user").last
    expect(user_msg.locator("img[src^='data:image/']")).to_be_visible(timeout=5_000)

    # Vision model should identify red. Scope to the latest assistant bubble
    # so we don't accidentally match stray "red" in headers/tooltips/etc.
    assistant = page.get_by_test_id("message-assistant").last
    reply = (assistant.text_content() or "").lower()
    assert "red" in reply, (
        f"Expected assistant reply to mention 'red'; got: {reply[:200]!r}"
    )
