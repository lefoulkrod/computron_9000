"""Unit tests for ``server._icloud_drive_routes`` — the preauth handlers.

These exercise the route handler logic with ``initiate_auth`` / ``complete_auth``
patched out — no Apple HTTP, no supervisor.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from integrations._icloud_auth import IcloudAuthError, IcloudAuthPasswordError
from server._icloud_drive_routes import (
    handle_icloud_drive_preauth_start,
    handle_icloud_drive_preauth_verify,
)


def _req(body: object) -> MagicMock:
    req = MagicMock()
    if isinstance(body, Exception):
        req.json = AsyncMock(side_effect=body)
    else:
        req.json = AsyncMock(return_value=body)
    return req


async def _resp_json(resp: object) -> dict:
    # web.json_response stores the serialized body on .text
    return json.loads(resp.text)  # type: ignore[attr-defined]


# --- start ------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_happy_path() -> None:
    with patch(
        "server._icloud_drive_routes.initiate_auth",
        AsyncMock(return_value={"session_id": "abc", "requires_2fa": True}),
    ):
        resp = await handle_icloud_drive_preauth_start(_req({"email": "x@icloud.com", "password": "pw"}))
    assert resp.status == 200
    assert await _resp_json(resp) == {"session_id": "abc", "requires_2fa": True}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_requires_email_and_password() -> None:
    resp = await handle_icloud_drive_preauth_start(_req({"password": "pw"}))
    assert resp.status == 400
    resp = await handle_icloud_drive_preauth_start(_req({"email": "x@icloud.com"}))
    assert resp.status == 400


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_bad_json() -> None:
    resp = await handle_icloud_drive_preauth_start(_req(json.JSONDecodeError("x", "y", 0)))
    assert resp.status == 400


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_password_rejected_maps_to_auth() -> None:
    with patch(
        "server._icloud_drive_routes.initiate_auth",
        AsyncMock(side_effect=IcloudAuthPasswordError("bad password")),
    ):
        resp = await handle_icloud_drive_preauth_start(_req({"email": "x@icloud.com", "password": "pw"}))
    assert resp.status == 409
    assert (await _resp_json(resp))["error"]["code"] == "AUTH"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_upstream_error_maps_to_502() -> None:
    with patch(
        "server._icloud_drive_routes.initiate_auth",
        AsyncMock(side_effect=IcloudAuthError("apple is down")),
    ):
        resp = await handle_icloud_drive_preauth_start(_req({"email": "x@icloud.com", "password": "pw"}))
    assert resp.status == 502


# --- verify -----------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_happy_path() -> None:
    with patch(
        "server._icloud_drive_routes.complete_auth",
        AsyncMock(return_value={"trust_token": "tok"}),
    ):
        resp = await handle_icloud_drive_preauth_verify(_req({"session_id": "abc", "code": "123456"}))
    assert resp.status == 200
    assert await _resp_json(resp) == {"trust_token": "tok"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_requires_session_and_code() -> None:
    resp = await handle_icloud_drive_preauth_verify(_req({"code": "123456"}))
    assert resp.status == 400
    resp = await handle_icloud_drive_preauth_verify(_req({"session_id": "abc"}))
    assert resp.status == 400


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_bad_code_maps_to_auth() -> None:
    with patch(
        "server._icloud_drive_routes.complete_auth",
        AsyncMock(side_effect=IcloudAuthError("wrong code")),
    ):
        resp = await handle_icloud_drive_preauth_verify(_req({"session_id": "abc", "code": "000000"}))
    assert resp.status == 409
    assert (await _resp_json(resp))["error"]["code"] == "AUTH"
