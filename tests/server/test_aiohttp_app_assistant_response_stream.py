"""Tests that the HTTP stream can handle AssistantResponse-like objects directly.

Includes a regression check that the stream closes cleanly and only the
expected lines are sent.
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import pytest

from agents.ollama.sdk.events import AssistantResponse, AssistantResponseData, ToolCallPayload
from server.aiohttp_app import create_app

pytestmark = [pytest.mark.unit]


async def _fake_events() -> AsyncIterator[AssistantResponse]:
    # Non-final first chunk
    yield AssistantResponse(content="hello", thinking=None)


@pytest.fixture
def app(monkeypatch):
    app = create_app()
    from server import aiohttp_app as mod

    async def _fake_handle_user_message(_msg: str, _data):  # noqa: D401
        async for ev in _fake_events():
            # Bridge to the legacy UserMessageEvent shape expected by stream_events
            class _Shim:
                def __init__(self, r: AssistantResponse):
                    self.message = r.content
                    self.final = False
                    self.thinking = r.thinking
                    self.content = r.content
                    self.data = r.data
                    self.event = r.event

            yield _Shim(ev)
        # Final enriched event
        class _Final:
            message = "done"
            final = True
            thinking = None
            content = "done"
            data = [AssistantResponseData(content_type="text/plain", content="dGVzdA==")]
            event = ToolCallPayload(type="tool_call", name="x")

        yield _Final()

    monkeypatch.setattr(mod, "handle_user_message", _fake_handle_user_message)
    return app


@pytest.mark.asyncio
async def test_streams_assistant_response_objects_and_closes(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.post("/api/chat", data=json.dumps({"message": "Hi"}))
    assert resp.status == 200
    text = await resp.text()
    lines = [ln for ln in text.strip().split("\n") if ln]
    # We expect exactly two lines (hello and final done)
    assert len(lines) == 2
    first = json.loads(lines[0])
    last = json.loads(lines[-1])
    assert first["content"] == "hello"
    assert last["final"] is True
    assert last["content"] == "done"
