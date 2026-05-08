"""Unit tests for the contacts tool modules under ``tools.integrations.contacts``."""

from __future__ import annotations

from typing import Any

import pytest

from integrations import broker_client
from tools.integrations.contacts.list_contacts import list_contacts
from tools.integrations.contacts.search_contacts import search_contacts


def _patch_call(monkeypatch: pytest.MonkeyPatch, *, result: Any = None, exc: Exception | None = None) -> None:
    """Replace ``broker_client.call`` with an async stub."""

    async def _fake(integration_id: str, verb: str, args: dict, *, app_sock_path: str) -> Any:
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr(broker_client, "call", _fake)


# ── list_contacts ─────────────────────────────────────��─────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_contacts_renders_name_email_phone(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(
        monkeypatch,
        result={"contacts": [
            {"name": "Alice Smith", "emails": ["alice@example.com"], "phones": ["+1-555-0100"], "organization": "Acme", "title": "CEO"},
            {"name": "Bob Jones", "emails": ["bob@example.com"], "phones": [], "organization": "", "title": ""},
        ]},
    )
    out = await list_contacts("gws_1")
    assert out == (
        "Contacts (2):\n"
        "- Alice Smith  <alice@example.com>  +1-555-0100  (CEO @ Acme)\n"
        "- Bob Jones  <bob@example.com>"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_contacts_shows_all_emails_and_phones(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(
        monkeypatch,
        result={"contacts": [
            {
                "name": "Alice Smith",
                "emails": ["alice@work.com", "alice@home.com"],
                "phones": ["+1-555-0001", "+1-555-0002"],
                "organization": "",
                "title": "",
            },
        ]},
    )
    out = await list_contacts("gws_1")
    assert out == (
        "Contacts (1):\n"
        "- Alice Smith  <alice@work.com>  <alice@home.com>  +1-555-0001  +1-555-0002"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_contacts_falls_back_to_email_when_no_name(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(
        monkeypatch,
        result={"contacts": [
            {"name": "", "emails": ["noreply@example.com"], "phones": [], "organization": "", "title": ""},
        ]},
    )
    out = await list_contacts("gws_1")
    assert out == (
        "Contacts (1):\n"
        "- noreply@example.com  <noreply@example.com>"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_contacts_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, result={"contacts": []})
    out = await list_contacts("gws_1")
    assert out == "No contacts found."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_contacts_reports_not_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("nope"))
    out = await list_contacts("gws_unknown")
    assert out == "Integration 'gws_unknown' is not connected."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_contacts_reports_generic_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationError("upstream boom"))
    out = await list_contacts("gws_1")
    assert out == "Failed to list contacts: upstream boom"


# ── search_contacts ─────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_contacts_renders_results(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(
        monkeypatch,
        result={"contacts": [
            {"name": "Alice Smith", "emails": ["alice@example.com"], "phones": [], "organization": "", "title": ""},
        ]},
    )
    out = await search_contacts("gws_1", "alice")
    assert out == (
        "Contact search results for 'alice' (1):\n"
        "- Alice Smith  <alice@example.com>"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_contacts_no_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, result={"contacts": []})
    out = await search_contacts("gws_1", "nobody")
    assert out == "No contacts matching 'nobody'."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_contacts_reports_not_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("nope"))
    out = await search_contacts("gws_unknown", "alice")
    assert out == "Integration 'gws_unknown' is not connected."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_contacts_reports_generic_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationError("upstream boom"))
    out = await search_contacts("gws_1", "alice")
    assert out == "Failed to search contacts: upstream boom"
