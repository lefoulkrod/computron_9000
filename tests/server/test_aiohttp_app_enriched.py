"""Additional tests for enriched streaming payload (content, data, event)."""

from __future__ import annotations

import json
from typing import AsyncIterator

import pytest
from aiohttp import web
from pydantic import BaseModel

from server.aiohttp_app import create_app

pytestmark = [pytest.mark.unit]


class _Event(BaseModel):
    final: bool
    thinking: str | None = None
    content: str | None = None


class _DataModel(BaseModel):
    content_type: str
    content: str


class _EventWithPayload(BaseModel):
    final: bool
    content: str | None = None
    data: list[_DataModel] = []
    event: dict[str, str] | None = None


async def _fake_events_enriched() -> AsyncIterator[object]:
    # first event content only
    yield _Event(final=False, content="hello")
    # second event with enriched fields
    yield _EventWithPayload(
        final=True,
        content="done",
        data=[_DataModel(content_type="text/plain", content="dGVzdA==")],
        event={"type": "tool_call", "name": "foo"},
    )


@pytest.fixture
def app(monkeypatch):
    app = create_app()
    from server import aiohttp_app as mod

    async def _fake_handle_user_message(_msg: str, _data) -> AsyncIterator[object]:  # noqa: D401
        async for ev in _fake_events_enriched():  # pragma: no branch
            yield ev

    monkeypatch.setattr(mod, "handle_user_message", _fake_handle_user_message)
    return app


@pytest.mark.asyncio
async def test_streaming_includes_enriched_fields(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.post("/api/chat", data=json.dumps({"message": "Hi"}))
    assert resp.status == 200
    text = await resp.text()
    lines = [ln for ln in text.strip().split("\n") if ln]
    # Second line should contain enriched payload
    enriched = json.loads(lines[-1])
    assert enriched["final"] is True
    # content present (legacy 'response' removed)
    assert enriched["content"] == "done"
    assert isinstance(enriched.get("data"), list)
    assert enriched["data"][0]["content_type"] == "text/plain"
    assert enriched["event"]["type"] == "tool_call"
