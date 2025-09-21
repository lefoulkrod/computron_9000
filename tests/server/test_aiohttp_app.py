"""Unit tests for aiohttp application factory and handlers."""

import json
from typing import AsyncIterator

import pytest
from aiohttp import web

from server.aiohttp_app import create_app

pytestmark = [pytest.mark.unit]


class _Event:
    def __init__(self, message: str, final: bool, thinking: str | None = None):
        self.message = message
        self.final = final
        self.thinking = thinking


async def _fake_events() -> AsyncIterator[_Event]:
    yield _Event("hello", False)
    yield _Event("world", True)


@pytest.fixture
def app(monkeypatch):
    app = create_app()
    # Patch handle_user_message to deterministic async generator
    from server import aiohttp_app as mod

    async def _fake_handle_user_message(_msg: str, _data) -> AsyncIterator[_Event]:  # noqa: D401
        async for ev in _fake_events():  # pragma: no branch
            yield ev

    monkeypatch.setattr(mod, "handle_user_message", _fake_handle_user_message)
    return app


@pytest.mark.asyncio
async def test_routes_exist(aiohttp_client, app):
    client = await aiohttp_client(app)
    # Index
    resp = await client.get("/")
    assert resp.status in (200, 404)  # 404 allowed if dist not built yet
    # Chat
    resp = await client.options("/api/chat")
    assert resp.status == 200
    assert resp.headers["Access-Control-Allow-Origin"] == "*"


@pytest.mark.asyncio
async def test_validation_error_returns_400(aiohttp_client, app):
    client = await aiohttp_client(app)
    # Missing required message field
    resp = await client.post("/api/chat", data=json.dumps({"not_message": "x"}))
    assert resp.status == 400
    body = await resp.json()
    assert "error" in body


@pytest.mark.asyncio
async def test_streaming_chat(aiohttp_client, app):
    client = await aiohttp_client(app)
    resp = await client.post("/api/chat", data=json.dumps({"message": "Hi"}))
    assert resp.status == 200
    text = await resp.text()
    # Expect two JSONL lines
    lines = [ln for ln in text.strip().split("\n") if ln]
    assert len(lines) == 2
    last = json.loads(lines[-1])
    assert last["final"] is True


@pytest.mark.asyncio
async def test_delete_history(aiohttp_client, app, monkeypatch):
    called = {}
    from agents import reset_message_history as real_reset
    # Patch where it's imported in the handler module
    def _fake_reset():  # noqa: D401 - simple stub
        called["yes"] = True
        return real_reset()
    monkeypatch.setattr("server.aiohttp_app.reset_message_history", _fake_reset)
    client = await aiohttp_client(app)
    resp = await client.delete("/api/chat/history")
    assert resp.status == 204
    assert called.get("yes") is True
