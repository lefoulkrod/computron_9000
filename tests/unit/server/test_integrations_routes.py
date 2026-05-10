"""Unit tests for ``server._integrations_routes``.

Covers the pure helpers (``_derive_suffix_from_email``) and the route
handler logic for LLM vs. non-LLM integrations — the add handler's
suffix derivation, permissions injection, and supervisor call arguments.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server._integrations_routes import _derive_suffix_from_email, handle_add_integration


# ── email-based suffix derivation ────────────────────────────────────────────


@pytest.mark.unit
def test_derive_suffix_returns_local_part_for_simple_address() -> None:
    assert _derive_suffix_from_email({"email": "alice@example.com"}) == "alice"


@pytest.mark.unit
def test_derive_suffix_lowercases_email() -> None:
    assert _derive_suffix_from_email({"email": "Alice@Example.com"}) == "alice"


@pytest.mark.unit
def test_derive_suffix_replaces_dots_and_pluses_with_dashes() -> None:
    assert _derive_suffix_from_email({"email": "alice.smith+work@x.com"}) == "alice-smith-work"


@pytest.mark.unit
def test_derive_suffix_collapses_dash_runs() -> None:
    assert _derive_suffix_from_email({"email": "a..b@x.com"}) == "a-b"


@pytest.mark.unit
def test_derive_suffix_strips_leading_and_trailing_dashes() -> None:
    assert _derive_suffix_from_email({"email": "-alice-@x.com"}) == "alice"


@pytest.mark.unit
def test_derive_suffix_preserves_underscore_and_dash() -> None:
    assert _derive_suffix_from_email({"email": "alice_smith-2@x.com"}) == "alice_smith-2"


@pytest.mark.unit
def test_derive_suffix_caps_at_48_chars() -> None:
    long_local = "a" * 100
    out = _derive_suffix_from_email({"email": f"{long_local}@x.com"})
    assert out is not None
    assert len(out) == 48
    assert out == "a" * 48


@pytest.mark.unit
def test_derive_suffix_returns_none_when_local_is_all_disallowed() -> None:
    assert _derive_suffix_from_email({"email": "++@x.com"}) is None


@pytest.mark.unit
def test_derive_suffix_handles_address_without_at_sign() -> None:
    assert _derive_suffix_from_email({"email": "noatsign"}) == "noatsign"


@pytest.mark.unit
def test_derive_suffix_returns_none_for_non_email_blob() -> None:
    assert _derive_suffix_from_email({"api_key": "sk-..."}) is None


@pytest.mark.unit
def test_derive_suffix_returns_none_when_no_email() -> None:
    assert _derive_suffix_from_email({}) is None


@pytest.mark.unit
def test_derive_suffix_returns_none_when_email_not_a_string() -> None:
    assert _derive_suffix_from_email({"email": 123}) is None  # type: ignore[arg-type]


@pytest.mark.unit
def test_derive_suffix_returns_none_when_auth_blob_is_none() -> None:
    assert _derive_suffix_from_email(None) is None


@pytest.mark.unit
def test_derive_suffix_returns_none_when_auth_blob_is_not_a_dict() -> None:
    assert _derive_suffix_from_email("not a dict") is None  # type: ignore[arg-type]


# ── handle_add_integration — LLM providers ──────────────────────────────────


def _make_add_request(body: dict) -> MagicMock:
    """Build a minimal aiohttp Request mock with a JSON body."""
    req = MagicMock()
    req.json = AsyncMock(return_value=body)
    return req


def _supervisor_ok(integration_id: str, slug: str) -> dict:
    """Minimal supervisor add response."""
    return {
        "id": integration_id,
        "slug": slug,
        "label": "Test",
        "permissions": {},
        "max_access": {},
        "capabilities": [],
        "state": "running",
        "socket": f"/run/cvault/{integration_id}.sock",
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_add_no_suffix_no_email_required() -> None:
    """LLM integrations don't require email and don't set user_suffix."""
    body = {"slug": "llm_openai", "label": "OpenAI", "auth_blob": {"api_key": "sk-test"}}
    captured_args = {}

    async def fake_supervisor_call(verb, args):
        captured_args.update(args)
        return _supervisor_ok("llm_openai", "llm_openai")

    with (
        patch("server._integrations_routes._supervisor_call", side_effect=fake_supervisor_call),
        patch("server._integrations_routes.mark_added"),
    ):
        resp = await handle_add_integration(_make_add_request(body))

    assert resp.status == 201
    assert "user_suffix" not in captured_args


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_add_injects_empty_permissions() -> None:
    """LLM integrations get permissions={} injected when the client omits it."""
    body = {"slug": "llm_anthropic", "label": "Anthropic", "auth_blob": {"api_key": "sk-test"}}
    captured_args = {}

    async def fake_supervisor_call(verb, args):
        captured_args.update(args)
        return _supervisor_ok("llm_anthropic", "llm_anthropic")

    with (
        patch("server._integrations_routes._supervisor_call", side_effect=fake_supervisor_call),
        patch("server._integrations_routes.mark_added"),
    ):
        resp = await handle_add_integration(_make_add_request(body))

    assert resp.status == 201
    assert captured_args["permissions"] == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_add_preserves_explicit_permissions() -> None:
    """If the client sends permissions for an LLM integration, don't overwrite."""
    body = {
        "slug": "llm_openai",
        "label": "OpenAI",
        "auth_blob": {"api_key": "sk-test"},
        "permissions": {"llm_proxy": "rw"},
    }
    captured_args = {}

    async def fake_supervisor_call(verb, args):
        captured_args.update(args)
        return _supervisor_ok("llm_openai", "llm_openai")

    with (
        patch("server._integrations_routes._supervisor_call", side_effect=fake_supervisor_call),
        patch("server._integrations_routes.mark_added"),
    ):
        resp = await handle_add_integration(_make_add_request(body))

    assert resp.status == 201
    assert captured_args["permissions"] == {"llm_proxy": "rw"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_non_llm_add_requires_email() -> None:
    """Non-LLM integrations without an email in auth_blob get 400."""
    body = {"slug": "icloud", "label": "iCloud", "auth_blob": {"password": "secret"}}

    resp = await handle_add_integration(_make_add_request(body))

    assert resp.status == 400
    data = json.loads(resp.body)
    assert "email" in data["error"]["message"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_non_llm_add_derives_suffix_from_email() -> None:
    """Non-LLM integrations derive user_suffix from auth_blob email."""
    body = {
        "slug": "icloud",
        "label": "iCloud",
        "auth_blob": {"email": "alice@example.com", "password": "secret"},
        "permissions": {"email": "rw"},
    }
    captured_args = {}

    async def fake_supervisor_call(verb, args):
        captured_args.update(args)
        return _supervisor_ok("icloud_alice", "icloud")

    with (
        patch("server._integrations_routes._supervisor_call", side_effect=fake_supervisor_call),
        patch("server._integrations_routes.mark_added"),
    ):
        resp = await handle_add_integration(_make_add_request(body))

    assert resp.status == 201
    assert captured_args["user_suffix"] == "alice"
