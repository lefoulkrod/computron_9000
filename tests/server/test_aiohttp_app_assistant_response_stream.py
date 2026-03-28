"""Tests that the HTTP stream can handle AgentEvent objects directly.

Includes a regression check that the stream closes cleanly and only the
expected lines are sent.
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import pytest

from sdk.events import AgentEvent, ContentPayload, ToolCallPayload, TurnEndPayload
from server.aiohttp_app import create_app

pytestmark = [pytest.mark.unit]


async def _fake_events() -> AsyncIterator[AgentEvent]:
    yield AgentEvent(payload=ContentPayload(type="content", content="hello"))


@pytest.fixture
def app(monkeypatch):
    app = create_app()
    from server import aiohttp_app as mod

    async def _fake_handle_user_message(_msg: str, _data, **_kwargs):  # noqa: D401
        async for ev in _fake_events():
            yield ev
        yield AgentEvent(payload=ContentPayload(type="content", content="done"))
        yield AgentEvent(payload=TurnEndPayload(type="turn_end"))

    monkeypatch.setattr(mod, "handle_user_message", _fake_handle_user_message)
    return app


@pytest.mark.asyncio
async def test_streams_agent_event_objects_and_closes(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.post("/api/chat", data=json.dumps({"message": "Hi"}))
    assert resp.status == 200
    text = await resp.text()
    lines = [ln for ln in text.strip().split("\n") if ln]
    # We expect three lines: hello, done content, turn_end
    assert len(lines) == 3
    first = json.loads(lines[0])
    last = json.loads(lines[-1])
    assert first["payload"]["content"] == "hello"
    assert last["payload"]["type"] == "turn_end"
