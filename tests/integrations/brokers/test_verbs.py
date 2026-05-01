"""Tests for ``brokers/email_broker/_verbs.py`` — the dispatcher logic only.

The dispatcher is pure routing: verb name -> client method -> response dict,
with a WRITE_ALLOWED gate in the middle. Tests use a tiny stub IMAP client
instead of the real ``ImapClient`` because what's under test is the dispatcher,
not IMAP. (Real IMAP coverage lives in ``test_imap_client.py`` and, later, in
subprocess-level broker tests.)
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from pathlib import Path

import pytest

from integrations._rpc import RpcError
from integrations.brokers.email_broker._verbs import VerbDispatcher
from integrations.brokers.email_broker.types import Mailbox, OutboundAttachment


class _StubImapClient:
    """Drop-in for ``ImapClient`` that records calls and returns canned data.

    Matches the real client's return type (``list[Mailbox]``) so the dispatcher
    exercises the same ``.model_dump()`` path it does in production. Tests
    seed canned responses by mutating attributes (``attachment_payload``,
    ``move_raises``, etc.) — same shape as a single configurable stub
    rather than a constellation of subclasses.
    """

    def __init__(self) -> None:
        self.list_mailboxes_calls = 0
        self.move_calls: list[tuple[str, str, str]] = []
        self.move_raises: Exception | None = None
        self.attachment_payload: bytes = b""
        self.attachment_filename: str = ""
        self.attachment_mime_type: str = ""
        self.attachment_raises: Exception | None = None

    async def list_mailboxes(self) -> list[Mailbox]:
        self.list_mailboxes_calls += 1
        return [
            Mailbox(name="INBOX", attrs=["\\HasNoChildren"]),
            Mailbox(name="Sent", attrs=["\\HasNoChildren"]),
        ]

    async def move_messages(
        self, folder: str, uids: list[str], dest_folder: str,
    ) -> None:
        if self.move_raises is not None:
            raise self.move_raises
        self.move_calls.append((folder, list(uids), dest_folder))

    async def fetch_attachment(
        self, folder: str, uid: str, attachment_id: str,
    ) -> tuple[bytes, str, str]:
        if self.attachment_raises is not None:
            raise self.attachment_raises
        return (
            self.attachment_payload,
            self.attachment_filename,
            self.attachment_mime_type,
        )


class _StubSmtp:
    """Drop-in for ``SmtpClient`` recording call args and returning a canned id."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send_message(
        self,
        *,
        to: list[str],
        subject: str,
        body: str,
        attachments: Sequence[OutboundAttachment] = (),
    ) -> str:
        self.calls.append({
            "to": to,
            "subject": subject,
            "body": body,
            "attachments": list(attachments),
        })
        return "<stub@id>"


@pytest.mark.asyncio
async def test_dispatch_list_mailboxes_calls_session_and_wraps_result(tmp_path: Path) -> None:
    """Happy path: the dispatcher calls the session method and wraps its
    return in the ``{"mailboxes": [...]}`` response envelope the app server
    expects.
    """
    imap = _StubImapClient()
    dispatcher = VerbDispatcher(imap=imap, smtp=None, write_allowed=False, attachments_dir=tmp_path)  # type: ignore[arg-type]

    result = await dispatcher.dispatch("list_mailboxes", {})

    assert imap.list_mailboxes_calls == 1
    assert result == {
        "mailboxes": [
            {"name": "INBOX", "attrs": ["\\HasNoChildren"]},
            {"name": "Sent", "attrs": ["\\HasNoChildren"]},
        ]
    }


@pytest.mark.asyncio
async def test_dispatch_unknown_verb_raises_bad_request(tmp_path: Path) -> None:
    """A verb that isn't in ``_VERB_TYPE`` is a typo or a client bug — the
    response distinguishes it from "declared but not yet implemented" below.
    """
    dispatcher = VerbDispatcher(imap=_StubImapClient(), smtp=None, write_allowed=True, attachments_dir=tmp_path)  # type: ignore[arg-type]

    with pytest.raises(RpcError) as excinfo:
        await dispatcher.dispatch("does_not_exist", {})

    assert excinfo.value.code == "BAD_REQUEST"
    assert excinfo.value.message == "unknown verb: does_not_exist"


@pytest.mark.asyncio
async def test_dispatch_write_verb_denied_when_write_not_allowed(tmp_path: Path) -> None:
    """WRITE_ALLOWED=false must refuse every write-classified verb locally,
    before the session is even consulted. This is the real security gate; a
    bash-run-capable agent bypassing the app-server registry still hits it.

    We use ``send_message`` because it's tagged ``write`` in the verb table and
    doesn't have a handler yet — proving the gate fires before handler lookup,
    not after.
    """
    imap = _StubImapClient()
    dispatcher = VerbDispatcher(imap=imap, smtp=None, write_allowed=False, attachments_dir=tmp_path)  # type: ignore[arg-type]

    with pytest.raises(RpcError) as excinfo:
        await dispatcher.dispatch("send_message", {"to": "a@b"})

    assert excinfo.value.code == "WRITE_DENIED"
    assert excinfo.value.message == "writes disabled for this integration"
    # And the client was not called — the gate fires before handler dispatch.
    assert imap.list_mailboxes_calls == 0


@pytest.mark.asyncio
async def test_dispatch_write_verb_allowed_falls_through_to_not_implemented(tmp_path: Path) -> None:
    """When WRITE_ALLOWED=true and SMTP isn't configured, ``send_message``
    is declared but unhandled and returns ``BAD_REQUEST "verb not implemented"``.
    Proves the gate passes and handler lookup is reached for the SMTP-less case.
    """
    dispatcher = VerbDispatcher(imap=_StubImapClient(), smtp=None, write_allowed=True, attachments_dir=tmp_path)  # type: ignore[arg-type]

    with pytest.raises(RpcError) as excinfo:
        await dispatcher.dispatch("send_message", {"to": ["a@b"]})

    assert excinfo.value.code == "BAD_REQUEST"
    assert excinfo.value.message == "verb not implemented: send_message"


@pytest.mark.asyncio
async def test_dispatch_send_message_calls_smtp_and_returns_message_id(tmp_path: Path) -> None:
    """Happy path: ``send_message`` with WRITE_ALLOWED=true and an SMTP
    client wired drives the SMTP call and returns the assigned Message-ID.
    """
    imap = _StubImapClient()
    smtp = _StubSmtp()
    dispatcher = VerbDispatcher(imap=imap, smtp=smtp, write_allowed=True, attachments_dir=tmp_path)  # type: ignore[arg-type]

    result = await dispatcher.dispatch(
        "send_message",
        {"to": ["a@b.com"], "subject": "hi", "body": "hello"},
    )

    assert result == {"sent": True, "message_id": "<stub@id>"}
    assert smtp.calls == [
        {"to": ["a@b.com"], "subject": "hi", "body": "hello", "attachments": []},
    ]


@pytest.mark.asyncio
async def test_dispatch_send_message_rejects_missing_to(tmp_path: Path) -> None:
    """``to`` is required and must be a non-empty array of strings."""
    smtp = _StubSmtp()
    dispatcher = VerbDispatcher(imap=_StubImapClient(), smtp=smtp, write_allowed=True, attachments_dir=tmp_path)  # type: ignore[arg-type]

    with pytest.raises(RpcError) as excinfo:
        await dispatcher.dispatch(
            "send_message", {"subject": "hi", "body": "hello"},
        )
    assert excinfo.value.code == "BAD_REQUEST"
    assert "'to'" in excinfo.value.message


@pytest.mark.asyncio
async def test_dispatch_send_message_decodes_attachments_and_passes_bytes(
    tmp_path: Path,
) -> None:
    """Happy path with attachments: bytes are base64-decoded once at the verb
    boundary so the SMTP client sees raw ``OutboundAttachment`` tuples, not
    the wire-level dicts."""
    smtp = _StubSmtp()
    dispatcher = VerbDispatcher(
        imap=_StubImapClient(), smtp=smtp,
        write_allowed=True, attachments_dir=tmp_path,  # type: ignore[arg-type]
    )

    payload = b"\x89PNG fake png"
    await dispatcher.dispatch(
        "send_message",
        {
            "to": ["a@b.com"],
            "subject": "hi",
            "body": "see attached",
            "attachments": [
                {
                    "filename": "logo.png",
                    "mime_type": "image/png",
                    "data_b64": base64.b64encode(payload).decode("ascii"),
                },
            ],
        },
    )

    assert smtp.calls[0]["attachments"] == [("logo.png", "image/png", payload)]


@pytest.mark.asyncio
async def test_dispatch_send_message_rejects_invalid_base64(tmp_path: Path) -> None:
    """Garbage in ``data_b64`` is a wire-level encoding bug — surface as BAD_REQUEST."""
    smtp = _StubSmtp()
    dispatcher = VerbDispatcher(
        imap=_StubImapClient(), smtp=smtp,
        write_allowed=True, attachments_dir=tmp_path,  # type: ignore[arg-type]
    )
    with pytest.raises(RpcError) as excinfo:
        await dispatcher.dispatch(
            "send_message",
            {
                "to": ["a@b.com"], "subject": "x", "body": "y",
                "attachments": [
                    {"filename": "f", "mime_type": "text/plain", "data_b64": "not!base64!"},
                ],
            },
        )
    assert excinfo.value.code == "BAD_REQUEST"
    assert "invalid base64" in excinfo.value.message


@pytest.mark.asyncio
async def test_dispatch_send_message_rejects_missing_attachment_fields(
    tmp_path: Path,
) -> None:
    """Each attachment must carry filename, mime_type, data_b64. Missing any
    is a BAD_REQUEST that names the offending index + field for debug.
    """
    smtp = _StubSmtp()
    dispatcher = VerbDispatcher(
        imap=_StubImapClient(), smtp=smtp,
        write_allowed=True, attachments_dir=tmp_path,  # type: ignore[arg-type]
    )
    with pytest.raises(RpcError) as excinfo:
        await dispatcher.dispatch(
            "send_message",
            {
                "to": ["a@b.com"], "subject": "x", "body": "y",
                "attachments": [
                    {"mime_type": "text/plain", "data_b64": ""},
                ],
            },
        )
    assert excinfo.value.code == "BAD_REQUEST"
    assert "attachments[0].filename" in excinfo.value.message


@pytest.mark.asyncio
async def test_dispatch_send_message_rejects_total_size_over_cap(
    tmp_path: Path,
) -> None:
    """The verb caps total raw attachment bytes (currently 30MB) so a
    runaway agent can't push payloads the upstream SMTP server will bounce —
    we want the BAD_REQUEST to fire here, before SMTP, so the agent gets
    actionable feedback rather than an opaque server reject.
    """
    smtp = _StubSmtp()
    dispatcher = VerbDispatcher(
        imap=_StubImapClient(), smtp=smtp,
        write_allowed=True, attachments_dir=tmp_path,  # type: ignore[arg-type]
    )
    # 31MB of zeros — one byte over the cap. b64 of 0x00*N is "AAAA..."
    big = base64.b64encode(b"\x00" * (31 * 1024 * 1024)).decode("ascii")
    with pytest.raises(RpcError) as excinfo:
        await dispatcher.dispatch(
            "send_message",
            {
                "to": ["a@b.com"], "subject": "x", "body": "y",
                "attachments": [
                    {"filename": "big.bin", "mime_type": "application/octet-stream", "data_b64": big},
                ],
            },
        )
    assert excinfo.value.code == "BAD_REQUEST"
    assert "30MB" in excinfo.value.message
    # Critically: the cap fires BEFORE the SMTP call. No half-built SMTP
    # transaction to clean up.
    assert smtp.calls == []


@pytest.mark.asyncio
async def test_dispatch_move_messages_calls_imap_and_returns_ack(tmp_path: Path) -> None:
    """Happy path: ``move_messages`` with WRITE_ALLOWED=true calls
    ``ImapClient.move_messages`` with the args from the frame and returns
    a thin ack. We don't surface a count because IMAP doesn't reliably
    report which UIDs actually moved.
    """
    imap = _StubImapClient()
    dispatcher = VerbDispatcher(imap=imap, smtp=None, write_allowed=True, attachments_dir=tmp_path)  # type: ignore[arg-type]

    result = await dispatcher.dispatch(
        "move_messages",
        {"folder": "INBOX", "uids": ["42", "43", "44"], "dest_folder": "Trash"},
    )

    assert result == {"moved": True}
    assert imap.move_calls == [("INBOX", ["42", "43", "44"], "Trash")]


@pytest.mark.asyncio
async def test_dispatch_move_messages_translates_lookup_error_to_not_found(tmp_path: Path) -> None:
    """``LookupError`` from the IMAP client (destination doesn't exist)
    surfaces as the wire-level ``NOT_FOUND`` code, not a generic error.
    """
    imap = _StubImapClient()
    imap.move_raises = LookupError("no such mailbox")
    dispatcher = VerbDispatcher(imap=imap, smtp=None, write_allowed=True, attachments_dir=tmp_path)  # type: ignore[arg-type]

    with pytest.raises(RpcError) as excinfo:
        await dispatcher.dispatch(
            "move_messages",
            {"folder": "INBOX", "uids": ["999"], "dest_folder": "Nowhere"},
        )
    assert excinfo.value.code == "NOT_FOUND"
    assert excinfo.value.message == "no such mailbox"


@pytest.mark.asyncio
async def test_dispatch_move_messages_rejects_empty_uids(tmp_path: Path) -> None:
    """Empty ``uids`` list is a usage error — surfaces BAD_REQUEST so the
    caller sees a clear "you didn't pass anything" error rather than a
    silent no-op."""
    imap = _StubImapClient()
    dispatcher = VerbDispatcher(imap=imap, smtp=None, write_allowed=True, attachments_dir=tmp_path)  # type: ignore[arg-type]

    with pytest.raises(RpcError) as excinfo:
        await dispatcher.dispatch(
            "move_messages",
            {"folder": "INBOX", "uids": [], "dest_folder": "Trash"},
        )
    assert excinfo.value.code == "BAD_REQUEST"
    assert imap.move_calls == []


@pytest.mark.asyncio
async def test_dispatch_move_messages_rejects_oversize_batch(tmp_path: Path) -> None:
    """200-uid cap is enforced at the verb layer so the broker never
    builds a wire frame the server might reject with a parse error."""
    imap = _StubImapClient()
    dispatcher = VerbDispatcher(imap=imap, smtp=None, write_allowed=True, attachments_dir=tmp_path)  # type: ignore[arg-type]

    with pytest.raises(RpcError) as excinfo:
        await dispatcher.dispatch(
            "move_messages",
            {
                "folder": "INBOX",
                "uids": [str(i) for i in range(201)],
                "dest_folder": "Trash",
            },
        )
    assert excinfo.value.code == "BAD_REQUEST"
    assert imap.move_calls == []


@pytest.mark.asyncio
async def test_dispatch_fetch_attachment_writes_bytes_to_dir(tmp_path: Path) -> None:
    """Happy path: handler receives bytes from IMAP, writes a file to the
    attachments dir keyed off the original filename, returns the path."""
    payload = b"\x89PNG fake png"
    imap = _StubImapClient()
    imap.attachment_payload = payload
    imap.attachment_filename = "photo.png"
    imap.attachment_mime_type = "image/png"
    dispatcher = VerbDispatcher(
        imap=imap, smtp=None, write_allowed=False, attachments_dir=tmp_path,  # type: ignore[arg-type]
    )

    result = await dispatcher.dispatch(
        "fetch_attachment",
        {"folder": "INBOX", "uid": "1", "attachment_id": "2"},
    )

    assert result["filename"] == "photo.png"
    assert result["mime_type"] == "image/png"
    assert result["size"] == len(payload)
    saved = Path(result["path"])
    assert saved.exists()
    assert saved.parent == tmp_path
    assert saved.read_bytes() == payload
    # Original filename used verbatim — collision dedupe only kicks in on
    # the second arrival.
    assert saved.name == "photo.png"


@pytest.mark.asyncio
async def test_dispatch_fetch_attachment_dedupes_on_filename_collision(
    tmp_path: Path,
) -> None:
    """A second attachment with the same filename gets an 8-char hex suffix
    so the first file isn't overwritten — same dedupe convention the
    virtual-computer uploads helper uses for chat-attached files.
    """
    imap = _StubImapClient()
    imap.attachment_payload = b"first"
    imap.attachment_filename = "doc.txt"
    imap.attachment_mime_type = "text/plain"
    dispatcher = VerbDispatcher(
        imap=imap, smtp=None, write_allowed=False, attachments_dir=tmp_path,  # type: ignore[arg-type]
    )

    first = await dispatcher.dispatch(
        "fetch_attachment",
        {"folder": "INBOX", "uid": "1", "attachment_id": "2"},
    )
    # Replace the canned bytes for the second call.
    imap.attachment_payload = b"second"
    second = await dispatcher.dispatch(
        "fetch_attachment",
        {"folder": "INBOX", "uid": "2", "attachment_id": "2"},
    )

    first_path = Path(first["path"])
    second_path = Path(second["path"])
    assert first_path != second_path
    assert first_path.name == "doc.txt"
    assert second_path.name.startswith("doc_")
    assert second_path.name.endswith(".txt")
    assert first_path.read_bytes() == b"first"
    assert second_path.read_bytes() == b"second"


@pytest.mark.asyncio
async def test_dispatch_fetch_attachment_translates_lookup_error_to_not_found(
    tmp_path: Path,
) -> None:
    """``LookupError`` from the IMAP client (no matching part) becomes the
    wire-level ``NOT_FOUND`` code."""
    imap = _StubImapClient()
    imap.attachment_raises = LookupError("no attachment 99")
    dispatcher = VerbDispatcher(
        imap=imap, smtp=None, write_allowed=False, attachments_dir=tmp_path,  # type: ignore[arg-type]
    )
    with pytest.raises(RpcError) as excinfo:
        await dispatcher.dispatch(
            "fetch_attachment",
            {"folder": "INBOX", "uid": "1", "attachment_id": "99"},
        )
    assert excinfo.value.code == "NOT_FOUND"
