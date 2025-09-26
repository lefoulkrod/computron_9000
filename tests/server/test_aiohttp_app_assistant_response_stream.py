"""Tests that the HTTP stream can handle AssistantResponse-like objects directly.

Includes a regression check that the stream closes cleanly and only the
expected lines are sent.
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import pytest
from pydantic import BaseModel

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

    class _ShimEvent(BaseModel):
        final: bool = False
        thinking: str | None = None
        content: str | None = None
        data: list[AssistantResponseData] | None = None
        event: ToolCallPayload | None = None

    class _FinalEvent(BaseModel):
        final: bool
        thinking: str | None
        content: str
        data: list[AssistantResponseData]
        event: ToolCallPayload | None = None

    async def _fake_handle_user_message(_msg: str, _data):  # noqa: D401
        async for ev in _fake_events():
            yield _ShimEvent(
                final=False,
                thinking=ev.thinking,
                content=ev.content,
                data=ev.data,
                event=ev.event,
            )
        yield _FinalEvent(
            final=True,
            thinking=None,
            content="done",
            data=[AssistantResponseData(content_type="text/plain", content="dGVzdA==")],
            event=ToolCallPayload(type="tool_call", name="x"),
        )

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
