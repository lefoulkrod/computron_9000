"""Unit tests for the four email-tool modules under ``tools.integrations``.

Each tool wraps exactly one ``broker_client.call`` and shapes the returned
dict into a plain-text string for the agent. These tests stub
``broker_client.call`` to return canned shapes (or raise) and assert on the
resulting string — no IMAP, no supervisor, no UDS, no real ``load_config``
side effects beyond reading the project ``config.yaml``.
"""

from __future__ import annotations

from typing import Any

import pytest

from integrations import broker_client
from tools.integrations.list_email_folders import list_email_folders
from tools.integrations.list_email_messages import list_email_messages
from tools.integrations.read_email_message import read_email_message
from tools.integrations.search_email import search_email


def _patch_call(monkeypatch: pytest.MonkeyPatch, *, result: Any = None, exc: Exception | None = None) -> None:
    """Replace ``broker_client.call`` with an async stub.

    Either returns ``result`` or raises ``exc`` once awaited. The stub
    ignores the ``app_sock_path`` kwarg — the tools pass it through but
    we don't care which value real ``load_config`` produced.
    """

    async def _fake(integration_id: str, verb: str, args: dict, *, app_sock_path: str) -> Any:
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr(broker_client, "call", _fake)


# ── list_email_folders ────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_email_folders_formats_each_mailbox_as_a_bullet(monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: a non-empty mailbox list renders one ``- name`` line per
    folder, headered with the integration ID so the agent can quote the
    source if asked.
    """
    _patch_call(
        monkeypatch,
        result={"mailboxes": [{"name": "INBOX"}, {"name": "Sent"}, {"name": "Trash"}]},
    )
    out = await list_email_folders("icloud_personal")
    assert out == (
        "Folders on 'icloud_personal':\n"
        "- INBOX\n"
        "- Sent\n"
        "- Trash"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_email_folders_returns_empty_notice_when_no_mailboxes(monkeypatch: pytest.MonkeyPatch) -> None:
    """An account with zero mailboxes (rare but possible) produces a single
    ``No folders found...`` line rather than a header with an empty list
    underneath.
    """
    _patch_call(monkeypatch, result={"mailboxes": []})
    out = await list_email_folders("icloud_personal")
    assert out == "No folders found on 'icloud_personal'."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_email_folders_reports_not_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    """``IntegrationNotConnected`` is the supervisor's "I don't know that
    id" signal — surface it as a friendly message naming the id, not the
    raw exception.
    """
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("unknown id"))
    out = await list_email_folders("icloud_unknown")
    assert out == "Integration 'icloud_unknown' is not connected."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_email_folders_reports_generic_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any other broker-side failure becomes a one-liner with the message
    appended — the agent surfaces it verbatim.
    """
    _patch_call(monkeypatch, exc=broker_client.IntegrationError("upstream boom"))
    out = await list_email_folders("icloud_personal")
    assert out == "Failed to list folders for 'icloud_personal': upstream boom"


# ── list_email_messages ──────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_email_messages_formats_envelopes_with_uid_brackets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each envelope renders as ``- [uid] date  sender  —  subject`` so the
    agent can round-trip the UID into ``read_email_message`` without any
    JSON parsing.
    """
    _patch_call(
        monkeypatch,
        result={"headers": [
            {"uid": "100", "date": "2026-04-25T09:00:00+00:00", "from_": "alice@x", "subject": "hi"},
            {"uid": "101", "date": "2026-04-25T10:00:00+00:00", "from_": "bob@y", "subject": "ping"},
        ]},
    )
    out = await list_email_messages("icloud_personal", "INBOX", limit=5)
    assert out == (
        "Recent messages in 'INBOX' (2):\n"
        "- [100] 2026-04-25T09:00:00+00:00  alice@x  —  hi\n"
        "- [101] 2026-04-25T10:00:00+00:00  bob@y  —  ping"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_email_messages_substitutes_placeholders_for_missing_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spammy mail with no From / Subject still produces a parseable line —
    we substitute ``(no sender)`` / ``(no subject)`` rather than dropping
    columns, so the formatting stays uniform.
    """
    _patch_call(monkeypatch, result={"headers": [{"uid": "1"}]})
    out = await list_email_messages("icloud_personal", "INBOX")
    assert out == (
        "Recent messages in 'INBOX' (1):\n"
        "- [1]   (no sender)  —  (no subject)"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_email_messages_returns_empty_notice(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty folder → single line, mentions the folder name."""
    _patch_call(monkeypatch, result={"headers": []})
    out = await list_email_messages("icloud_personal", "Drafts")
    assert out == "No messages in 'Drafts'."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_email_messages_reports_not_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("nope"))
    out = await list_email_messages("icloud_unknown", "INBOX")
    assert out == "Integration 'icloud_unknown' is not connected."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_email_messages_reports_generic_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationError("upstream boom"))
    out = await list_email_messages("icloud_personal", "INBOX")
    assert out == "Failed to list messages in 'INBOX': upstream boom"


# ── read_email_message ──────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_read_email_message_renders_header_block_and_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typical message produces a ``From: / To: / Date: / Subject:`` block
    followed by a blank line and the plain-text body.
    """
    _patch_call(
        monkeypatch,
        result={"message": {
            "header": {
                "from_": "alice@x",
                "to": "bob@y",
                "date": "2026-04-25T09:00:00+00:00",
                "subject": "hi",
            },
            "body_text": "Hello there.",
        }},
    )
    out = await read_email_message("icloud_personal", "INBOX", "100")
    assert out == (
        "From: alice@x\n"
        "To: bob@y\n"
        "Date: 2026-04-25T09:00:00+00:00\n"
        "Subject: hi\n"
        "\n"
        "Hello there."
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_read_email_message_handles_empty_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """An attachments-only message has no text part — emit a placeholder
    instead of returning a header block with nothing under it.
    """
    _patch_call(
        monkeypatch,
        result={"message": {
            "header": {"from_": "a@b", "to": "", "date": "", "subject": "blob"},
            "body_text": "",
        }},
    )
    out = await read_email_message("icloud_personal", "INBOX", "100")
    assert out == (
        "From: a@b\n"
        "To: \n"
        "Date: \n"
        "Subject: blob\n"
        "\n"
        "(no text body)"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_read_email_message_reports_not_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("nope"))
    out = await read_email_message("icloud_unknown", "INBOX", "1")
    assert out == "Integration 'icloud_unknown' is not connected."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_read_email_message_reports_generic_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generic errors include both the UID and the folder so the user can
    diagnose without guessing which message we tried to fetch.
    """
    _patch_call(monkeypatch, exc=broker_client.IntegrationError("upstream boom"))
    out = await read_email_message("icloud_personal", "INBOX", "42")
    assert out == "Failed to read message 42 in 'INBOX': upstream boom"


# ── search_email ────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_email_formats_matches_with_query_in_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """Search results use the same envelope format as ``list_email_messages``
    so the agent can chain into ``read_email_message`` regardless of which
    tool produced the UID.
    """
    _patch_call(
        monkeypatch,
        result={"headers": [
            {"uid": "7", "date": "2026-04-25T09:00:00+00:00", "from_": "alice@x", "subject": "invoice"},
        ]},
    )
    out = await search_email("icloud_personal", "invoice")
    assert out == (
        "Matches for 'invoice' in 'INBOX' (1):\n"
        "- [7] 2026-04-25T09:00:00+00:00  alice@x  —  invoice"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_email_returns_empty_notice_naming_query_and_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    """No matches → one line that quotes both the query and the folder, so
    the agent can decide whether to retry in another folder or give up.
    """
    _patch_call(monkeypatch, result={"headers": []})
    out = await search_email("icloud_personal", "needle", folder="Sent")
    assert out == "No matches for 'needle' in 'Sent'."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_email_uses_inbox_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default folder is INBOX; verify the call shape carries that default
    (rather than the broker silently using its own default)."""
    captured: dict[str, Any] = {}

    async def _capture(integration_id: str, verb: str, args: dict, *, app_sock_path: str) -> Any:
        captured["args"] = args
        return {"headers": []}

    monkeypatch.setattr(broker_client, "call", _capture)
    await search_email("icloud_personal", "anything")
    assert captured["args"]["folder"] == "INBOX"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_email_reports_not_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("nope"))
    out = await search_email("icloud_unknown", "anything")
    assert out == "Integration 'icloud_unknown' is not connected."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_email_reports_generic_error_naming_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationError("upstream boom"))
    out = await search_email("icloud_personal", "anything", folder="Archive")
    assert out == "Failed to search 'Archive': upstream boom"
