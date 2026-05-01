"""Tests for the public HTTP handlers in ``server.aiohttp_app``.

Focused on input validation at the API edge — the chat / stop /
delete-history endpoints must reject requests without a
``conversation_id`` instead of silently falling back to a shared
"default" conversation.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from server.aiohttp_app import (
    chat_handler,
    delete_history_handler,
    stop_handler,
)


def _make_request(*, raw_body: str | None = None, query: dict | None = None) -> MagicMock:
    """Build a minimal aiohttp.web.Request-ish double."""
    req = MagicMock()
    req.query = query or {}
    if raw_body is not None:
        req.text = AsyncMock(return_value=raw_body)
    return req


# -- chat_handler -----------------------------------------------------------


@pytest.mark.unit
async def test_chat_missing_conversation_id_returns_400() -> None:
    """No conversation_id field → 400 with a clear error message."""
    req = _make_request(raw_body=json.dumps({
        "message": "hi",
        "profile_id": "computron",
    }))
    resp = await chat_handler(req)
    assert resp.status == 400
    body = json.loads(resp.body)
    assert body["error"] == "conversation_id is required."


@pytest.mark.unit
async def test_chat_null_conversation_id_returns_400() -> None:
    """Explicit null conversation_id → 400."""
    req = _make_request(raw_body=json.dumps({
        "message": "hi",
        "profile_id": "computron",
        "conversation_id": None,
    }))
    resp = await chat_handler(req)
    assert resp.status == 400


@pytest.mark.unit
async def test_chat_empty_conversation_id_returns_400() -> None:
    """Empty-string conversation_id → 400."""
    req = _make_request(raw_body=json.dumps({
        "message": "hi",
        "profile_id": "computron",
        "conversation_id": "",
    }))
    resp = await chat_handler(req)
    assert resp.status == 400


@pytest.mark.unit
async def test_chat_missing_message_returns_400() -> None:
    """Pre-existing behavior preserved: empty message also rejected."""
    req = _make_request(raw_body=json.dumps({
        "message": "   ",
        "profile_id": "computron",
        "conversation_id": "abc",
    }))
    resp = await chat_handler(req)
    assert resp.status == 400
    body = json.loads(resp.body)
    assert body["error"] == "Message field is required."


# -- stop_handler -----------------------------------------------------------


@pytest.mark.unit
async def test_stop_missing_conversation_id_returns_400() -> None:
    """No conversation_id query param → 400."""
    req = _make_request(query={})
    resp = await stop_handler(req)
    assert resp.status == 400
    body = json.loads(resp.body)
    assert body["error"] == "conversation_id is required."


@pytest.mark.unit
async def test_stop_empty_conversation_id_returns_400() -> None:
    """Empty conversation_id query value → 400."""
    req = _make_request(query={"conversation_id": ""})
    resp = await stop_handler(req)
    assert resp.status == 400


# -- delete_history_handler -------------------------------------------------


@pytest.mark.unit
async def test_delete_history_missing_conversation_id_returns_400() -> None:
    """No conversation_id query param → 400."""
    req = _make_request(query={})
    resp = await delete_history_handler(req)
    assert resp.status == 400
    body = json.loads(resp.body)
    assert body["error"] == "conversation_id is required."


@pytest.mark.unit
async def test_delete_history_empty_conversation_id_returns_400() -> None:
    """Empty conversation_id query value → 400."""
    req = _make_request(query={"conversation_id": ""})
    resp = await delete_history_handler(req)
    assert resp.status == 400
