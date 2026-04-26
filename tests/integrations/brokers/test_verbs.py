"""Tests for ``brokers/email_broker/_verbs.py`` — the dispatcher logic only.

The dispatcher is pure routing: verb name -> client method -> response dict,
with a WRITE_ALLOWED gate in the middle. Tests use a tiny stub IMAP client
instead of the real ``ImapClient`` because what's under test is the dispatcher,
not IMAP. (Real IMAP coverage lives in ``test_imap_client.py`` and, later, in
subprocess-level broker tests.)
"""

from __future__ import annotations

import pytest

from integrations._rpc import RpcError
from integrations.brokers.email_broker._verbs import VerbDispatcher
from integrations.brokers.email_broker.types import Mailbox


class _StubImap:
    """Drop-in for ``ImapClient`` that records calls and returns canned data.

    Matches the real client's return type (``list[Mailbox]``) so the dispatcher
    exercises the same ``.model_dump()`` path it does in production.
    """

    def __init__(self) -> None:
        self.list_mailboxes_calls = 0
        self.move_calls: list[tuple[str, str, str]] = []
        self.move_raises: Exception | None = None

    async def list_mailboxes(self) -> list[Mailbox]:
        self.list_mailboxes_calls += 1
        return [
            Mailbox(name="INBOX", attrs=["\\HasNoChildren"]),
            Mailbox(name="Sent", attrs=["\\HasNoChildren"]),
        ]

    async def move_message(self, folder: str, uid: str, dest_folder: str) -> None:
        if self.move_raises is not None:
            raise self.move_raises
        self.move_calls.append((folder, uid, dest_folder))


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
    ) -> str:
        self.calls.append({"to": to, "subject": subject, "body": body})
        return "<stub@id>"


@pytest.mark.asyncio
async def test_dispatch_list_mailboxes_calls_session_and_wraps_result() -> None:
    """Happy path: the dispatcher calls the session method and wraps its
    return in the ``{"mailboxes": [...]}`` response envelope the app server
    expects.
    """
    imap = _StubImap()
    dispatcher = VerbDispatcher(imap=imap, smtp=None, write_allowed=False)  # type: ignore[arg-type]

    result = await dispatcher.dispatch("list_mailboxes", {})

    assert imap.list_mailboxes_calls == 1
    assert result == {
        "mailboxes": [
            {"name": "INBOX", "attrs": ["\\HasNoChildren"]},
            {"name": "Sent", "attrs": ["\\HasNoChildren"]},
        ]
    }


@pytest.mark.asyncio
async def test_dispatch_unknown_verb_raises_bad_request() -> None:
    """A verb that isn't in ``_VERB_TYPE`` is a typo or a client bug — the
    response distinguishes it from "declared but not yet implemented" below.
    """
    dispatcher = VerbDispatcher(imap=_StubImap(), smtp=None, write_allowed=True)  # type: ignore[arg-type]

    with pytest.raises(RpcError) as excinfo:
        await dispatcher.dispatch("does_not_exist", {})

    assert excinfo.value.code == "BAD_REQUEST"
    assert excinfo.value.message == "unknown verb: does_not_exist"


@pytest.mark.asyncio
async def test_dispatch_write_verb_denied_when_write_not_allowed() -> None:
    """WRITE_ALLOWED=false must refuse every write-classified verb locally,
    before the session is even consulted. This is the real security gate; a
    bash-run-capable agent bypassing the app-server registry still hits it.

    We use ``send_message`` because it's tagged ``write`` in the verb table and
    doesn't have a handler yet — proving the gate fires before handler lookup,
    not after.
    """
    imap = _StubImap()
    dispatcher = VerbDispatcher(imap=imap, smtp=None, write_allowed=False)  # type: ignore[arg-type]

    with pytest.raises(RpcError) as excinfo:
        await dispatcher.dispatch("send_message", {"to": "a@b"})

    assert excinfo.value.code == "WRITE_DENIED"
    assert excinfo.value.message == "writes disabled for this integration"
    # And the client was not called — the gate fires before handler dispatch.
    assert imap.list_mailboxes_calls == 0


@pytest.mark.asyncio
async def test_dispatch_write_verb_allowed_falls_through_to_not_implemented() -> None:
    """When WRITE_ALLOWED=true and SMTP isn't configured, ``send_message``
    is declared but unhandled and returns ``BAD_REQUEST "verb not implemented"``.
    Proves the gate passes and handler lookup is reached for the SMTP-less case.
    """
    dispatcher = VerbDispatcher(imap=_StubImap(), smtp=None, write_allowed=True)  # type: ignore[arg-type]

    with pytest.raises(RpcError) as excinfo:
        await dispatcher.dispatch("send_message", {"to": ["a@b"]})

    assert excinfo.value.code == "BAD_REQUEST"
    assert excinfo.value.message == "verb not implemented: send_message"


@pytest.mark.asyncio
async def test_dispatch_send_message_calls_smtp_and_returns_message_id() -> None:
    """Happy path: ``send_message`` with WRITE_ALLOWED=true and an SMTP
    client wired drives the SMTP call and returns the assigned Message-ID.
    """
    imap = _StubImap()
    smtp = _StubSmtp()
    dispatcher = VerbDispatcher(imap=imap, smtp=smtp, write_allowed=True)  # type: ignore[arg-type]

    result = await dispatcher.dispatch(
        "send_message",
        {"to": ["a@b.com"], "subject": "hi", "body": "hello"},
    )

    assert result == {"sent": True, "message_id": "<stub@id>"}
    assert smtp.calls == [
        {"to": ["a@b.com"], "subject": "hi", "body": "hello"},
    ]


@pytest.mark.asyncio
async def test_dispatch_send_message_rejects_missing_to() -> None:
    """``to`` is required and must be a non-empty array of strings."""
    smtp = _StubSmtp()
    dispatcher = VerbDispatcher(imap=_StubImap(), smtp=smtp, write_allowed=True)  # type: ignore[arg-type]

    with pytest.raises(RpcError) as excinfo:
        await dispatcher.dispatch(
            "send_message", {"subject": "hi", "body": "hello"},
        )
    assert excinfo.value.code == "BAD_REQUEST"
    assert "'to'" in excinfo.value.message


@pytest.mark.asyncio
async def test_dispatch_move_message_calls_imap_and_returns_ack() -> None:
    """Happy path: ``move_message`` with WRITE_ALLOWED=true calls
    ``ImapClient.move_message`` with the args from the frame.
    """
    imap = _StubImap()
    dispatcher = VerbDispatcher(imap=imap, smtp=None, write_allowed=True)  # type: ignore[arg-type]

    result = await dispatcher.dispatch(
        "move_message",
        {"folder": "INBOX", "uid": "42", "dest_folder": "Trash"},
    )

    assert result == {"moved": True}
    assert imap.move_calls == [("INBOX", "42", "Trash")]


@pytest.mark.asyncio
async def test_dispatch_move_message_translates_lookup_error_to_not_found() -> None:
    """``LookupError`` from the IMAP client (no such UID / no such mailbox)
    surfaces as the wire-level ``NOT_FOUND`` code, not a generic error.
    """
    imap = _StubImap()
    imap.move_raises = LookupError("no such message")
    dispatcher = VerbDispatcher(imap=imap, smtp=None, write_allowed=True)  # type: ignore[arg-type]

    with pytest.raises(RpcError) as excinfo:
        await dispatcher.dispatch(
            "move_message",
            {"folder": "INBOX", "uid": "999", "dest_folder": "Trash"},
        )
    assert excinfo.value.code == "NOT_FOUND"
    assert excinfo.value.message == "no such message"
