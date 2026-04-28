"""Unit tests for the four email-tool modules under ``tools.integrations``.

Each tool wraps exactly one ``broker_client.call`` and shapes the returned
dict into a plain-text string for the agent. These tests stub
``broker_client.call`` to return canned shapes (or raise) and assert on the
resulting string — no IMAP, no supervisor, no UDS, no real ``load_config``
side effects beyond reading the project ``config.yaml``.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest

from integrations import broker_client
from tools.integrations.download_email_attachment import download_email_attachment
from tools.integrations.list_email_folders import list_email_folders
from tools.integrations.list_email_messages import list_email_messages
from tools.integrations.move_email import move_email
from tools.integrations.read_email_message import read_email_message
from tools.integrations.search_email import search_email
from tools.integrations.send_email import send_email


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


# ── send_email ───────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_email_confirms_with_message_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: the broker returns a Message-ID; the tool surfaces it so
    the agent can quote the assigned ID back to the user.
    """
    _patch_call(
        monkeypatch,
        result={"sent": True, "message_id": "<abc@me.com>"},
    )
    out = await send_email(
        "icloud_personal", to=["a@b.com"], subject="hi", body="hello",
    )
    assert out == (
        "Sent via 'icloud_personal' to a@b.com (Message-ID: <abc@me.com>)."
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_email_lists_multiple_recipients(monkeypatch: pytest.MonkeyPatch) -> None:
    """Multiple ``to`` addresses are joined with ", " in the confirmation."""
    _patch_call(monkeypatch, result={"sent": True, "message_id": "<x@y>"})
    out = await send_email(
        "icloud_personal", to=["a@b.com", "c@d.com"], subject="s", body="b",
    )
    assert "to a@b.com, c@d.com" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_email_falls_back_when_message_id_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the broker omits ``message_id`` (older broker / unparsed response),
    the confirmation drops the parenthetical instead of showing an empty
    Message-ID parenthesis.
    """
    _patch_call(monkeypatch, result={"sent": True})
    out = await send_email(
        "icloud_personal", to=["a@b.com"], subject="s", body="b",
    )
    assert out == "Sent via 'icloud_personal' to a@b.com."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_email_reports_not_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("nope"))
    out = await send_email(
        "icloud_unknown", to=["a@b.com"], subject="s", body="b",
    )
    assert out == "Integration 'icloud_unknown' is not connected."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_email_reports_write_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the broker rejects under WRITE_DENIED (writes off for this
    integration), the agent gets a specific message — different from a
    generic upstream failure so the caller knows the fix is to flip the
    write_allowed bit, not to retry.
    """
    _patch_call(monkeypatch, exc=broker_client.IntegrationWriteDenied("denied"))
    out = await send_email(
        "icloud_personal", to=["a@b.com"], subject="s", body="b",
    )
    assert out == "Writes are disabled for 'icloud_personal'."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_email_reports_generic_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationError("smtp down"))
    out = await send_email(
        "icloud_personal", to=["a@b.com"], subject="s", body="b",
    )
    assert out == "Failed to send via 'icloud_personal': smtp down"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_email_reads_attachment_paths_and_encodes_to_broker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """The tool reads each attachment path off disk, derives a mime_type from
    the extension, and base64-encodes the bytes before handing the structured
    list to the broker. The broker side never sees the raw filesystem path.
    """
    payload = b"\x89PNG fake-png-bytes"
    attachment = tmp_path / "logo.png"
    attachment.write_bytes(payload)

    captured: dict[str, Any] = {}

    async def _capture(integration_id: str, verb: str, args: dict, *, app_sock_path: str) -> Any:
        captured["args"] = args
        return {"sent": True, "message_id": "<abc@me.com>"}

    monkeypatch.setattr(broker_client, "call", _capture)

    await send_email(
        "icloud_personal",
        to=["a@b.com"],
        subject="hi",
        body="see attached",
        attachments=[str(attachment)],
    )

    sent_attachments = captured["args"]["attachments"]
    assert len(sent_attachments) == 1
    item = sent_attachments[0]
    assert item["filename"] == "logo.png"
    assert item["mime_type"] == "image/png"
    assert base64.b64decode(item["data_b64"]) == payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_email_reports_missing_attachment_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """A path that doesn't exist surfaces as a plain-text error. Critically,
    the broker is never called — we don't want a partial transaction where
    the message goes out without the attachment the agent thought it was
    sending.
    """
    called = False

    async def _called(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(broker_client, "call", _called)

    missing = tmp_path / "does_not_exist.pdf"
    out = await send_email(
        "icloud_personal",
        to=["a@b.com"],
        subject="hi",
        body="x",
        attachments=[str(missing)],
    )

    assert "Cannot read attachment" in out
    assert str(missing) in out
    assert called is False


# ── move_email ───────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_move_email_confirms_move(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, result={"moved": True})
    out = await move_email("icloud_personal", "INBOX", "42", "Archive")
    assert out == "Moved '42' from 'INBOX' to 'Archive'."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_move_email_passes_args_through(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def _capture(integration_id: str, verb: str, args: dict, *, app_sock_path: str) -> Any:
        captured["args"] = args
        return {"moved": True}

    monkeypatch.setattr(broker_client, "call", _capture)
    await move_email("icloud_personal", "INBOX", "42", "Trash")
    assert captured["args"] == {"folder": "INBOX", "uid": "42", "dest_folder": "Trash"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_move_email_reports_not_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("nope"))
    out = await move_email("icloud_unknown", "INBOX", "42", "Archive")
    assert out == "Integration 'icloud_unknown' is not connected."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_move_email_reports_write_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationWriteDenied("denied"))
    out = await move_email("icloud_personal", "INBOX", "42", "Archive")
    assert out == "Writes are disabled for 'icloud_personal'."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_move_email_reports_generic_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationError("no such mailbox"))
    out = await move_email("icloud_personal", "INBOX", "42", "Nowhere")
    assert out == "Failed to move '42' from 'INBOX' to 'Nowhere': no such mailbox"


# ── read_email_message attachments rendering ─────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_read_email_message_lists_attachments_with_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a message carries attachments the header block grows an
    ``Attachments:`` section with one line per attachment — id, filename,
    mime, and a human-readable size — so the agent can quote the id back
    to ``download_email_attachment``.
    """
    _patch_call(
        monkeypatch,
        result={"message": {
            "header": {
                "from_": "alice@x", "to": "bob@y",
                "date": "2026-04-26T09:00:00+00:00", "subject": "files",
            },
            "body_text": "see attached",
            "attachments": [
                {"id": "2", "filename": "resume.pdf",
                 "mime_type": "application/pdf", "size": 245_120},
                {"id": "3", "filename": "photo.jpg",
                 "mime_type": "image/jpeg", "size": 1_258_291},
            ],
        }},
    )
    out = await read_email_message("icloud_personal", "INBOX", "100")
    assert "Attachments:" in out
    assert "id=2  resume.pdf  (application/pdf, 239.4KB)" in out
    assert "id=3  photo.jpg  (image/jpeg, 1.2MB)" in out
    assert "see attached" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_read_email_message_omits_attachments_section_when_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A message with no attachments doesn't render an empty
    ``Attachments:`` line — the section disappears entirely."""
    _patch_call(
        monkeypatch,
        result={"message": {
            "header": {
                "from_": "alice@x", "to": "bob@y",
                "date": "2026-04-26T09:00:00+00:00", "subject": "hi",
            },
            "body_text": "no files here",
            "attachments": [],
        }},
    )
    out = await read_email_message("icloud_personal", "INBOX", "100")
    assert "Attachments" not in out


# ── download_email_attachment ────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_download_email_attachment_returns_path_and_filename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path: confirmation includes the original filename, the saved
    path the agent passes to downstream tools, and a human-readable size.
    """
    _patch_call(
        monkeypatch,
        result={
            "path": "/home/computron/uploads/resume.pdf",
            "filename": "resume.pdf",
            "mime_type": "application/pdf",
            "size": 245_120,
        },
    )
    out = await download_email_attachment(
        "icloud_personal", "INBOX", "100", "2",
    )
    assert out == (
        "Saved 'resume.pdf' to /home/computron/uploads/resume.pdf (239.4KB)."
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_download_email_attachment_reports_not_connected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_call(monkeypatch, exc=broker_client.IntegrationNotConnected("nope"))
    out = await download_email_attachment(
        "icloud_unknown", "INBOX", "100", "2",
    )
    assert out == "Integration 'icloud_unknown' is not connected."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_download_email_attachment_reports_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_call(
        monkeypatch,
        exc=broker_client.IntegrationError("no attachment '99' in uid=100"),
    )
    out = await download_email_attachment(
        "icloud_personal", "INBOX", "100", "99",
    )
    assert out == (
        "Failed to download attachment '99' from '100': "
        "no attachment '99' in uid=100"
    )
