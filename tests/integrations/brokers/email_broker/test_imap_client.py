"""Tests for brokers/email_broker/_imap_client.py against the fake_email fixture.

Integration-style — real TCP between stdlib ``imaplib`` (running in a worker
thread via ``asyncio.to_thread``) and ``fake_email``'s asyncio IMAP server bound
on a kernel-chosen random port. Nothing is mocked at the socket layer, so these
tests exercise both the client class and the fake in one pass; if either is
wrong, the test fails.

Each test spins up its own ``FakeEmail`` instance rather than using a pytest
fixture. Two reasons:

1. The failure-mode tests mutate server state (``reject_next_n_imap_logins``,
   etc.), so sharing an instance across tests would cross-contaminate.
2. FakeEmail is cheap to start/stop (~low ms), so the per-test cost is small
   and the test file stays explicit about the server's lifecycle.
"""

from __future__ import annotations

import pytest

from integrations.brokers.email_broker._imap_client import ImapAuthError, ImapClient
from tests.integrations.fixtures.fake_email import FakeEmail


async def _connected_client(fake: FakeEmail) -> ImapClient:
    """Build + connect an ImapClient pointed at ``fake``. Plain TCP, no TLS."""
    client = ImapClient(
        host=fake.imap_host,
        port=fake.imap_port,
        user=fake.user,
        password=fake.password,
        use_tls=False,
    )
    await client.connect()
    return client


@pytest.mark.asyncio
async def test_connect_and_list_mailboxes_returns_default_set() -> None:
    """Happy path: LOGIN ok, LIST returns INBOX / Sent / Trash.

    Proves end-to-end that the client's ``connect()`` handshakes correctly with
    an RFC-3501 server, and that ``list_mailboxes()`` parses the raw ``LIST``
    output (``(\\HasNoChildren) "/" "INBOX"``-style lines) into ``Mailbox``
    instances the verb handlers expect.
    """
    fake = FakeEmail()
    await fake.start()
    try:
        client = ImapClient(
            host=fake.imap_host,
            port=fake.imap_port,
            user=fake.user,
            password=fake.password,
            # The fake speaks plain TCP — production uses 993/TLS, but there's
            # no point making the fake deal with certificates.
            use_tls=False,
        )
        await client.connect()
        mailboxes = await client.list_mailboxes()
    finally:
        # try/finally — not pytest's addfinalizer — so a failed assertion above
        # still releases the listener socket. An orphaned FakeEmail would leave
        # a port bound and spam asyncio warnings into later tests.
        await fake.stop()

    names = sorted(m.name for m in mailboxes)
    # FakeEmail seeds these three by default; if we ever add more defaults the
    # test should be updated in lockstep.
    assert names == ["INBOX", "Sent", "Trash"]
    # Every row should carry a (possibly empty) flag list — confirms the parser
    # didn't accidentally drop the attrs field for any mailbox.
    assert all(isinstance(m.attrs, list) for m in mailboxes)


@pytest.mark.asyncio
async def test_connect_raises_imap_auth_error_when_login_rejected() -> None:
    """Persistent LOGIN rejection raises ``ImapAuthError``, the sentinel the
    broker's ``__main__`` maps to ``sys.exit(77)`` so the supervisor flips
    state to ``auth_failed`` and stops restarting.

    We force ONE rejection because ``ImapClient.connect()`` makes a single
    LOGIN attempt — it does not retry on its own. The broker-level 3-fail
    reconnect policy lives at a higher layer.
    """
    fake = FakeEmail()
    await fake.start()
    try:
        fake.reject_next_n_imap_logins = 1
        client = ImapClient(
            host=fake.imap_host,
            port=fake.imap_port,
            user=fake.user,
            password=fake.password,
            use_tls=False,
        )
        with pytest.raises(ImapAuthError):
            await client.connect()
    finally:
        await fake.stop()


@pytest.mark.asyncio
async def test_move_messages_relocates_message_between_mailboxes() -> None:
    """Happy path: ``move_messages`` with one UID moves a real seeded
    message from INBOX to Trash. After the move, INBOX is empty and Trash
    has the message — proves UID MOVE worked, not just COPY (which would
    leave a duplicate).
    """
    fake = FakeEmail()
    await fake.start()
    try:
        uid = fake.add_message(
            "INBOX",
            from_="alice@example.com",
            to=fake.user,
            subject="bye",
            body="going to trash",
        )
        client = await _connected_client(fake)
        await client.move_messages("INBOX", [str(uid)], "Trash")
    finally:
        await fake.stop()

    assert fake.mailboxes["INBOX"].messages == []
    assert len(fake.mailboxes["Trash"].messages) == 1
    record = fake.mailboxes["Trash"].messages[0]
    assert b"Subject: bye" in record.raw


@pytest.mark.asyncio
async def test_move_messages_bulk_moves_multiple_uids_in_one_call() -> None:
    """Multiple UIDs in one call land on the destination together — the
    real win of bulk move. Verifies the comma-joined UID set parses on
    the server and every message ends up in the destination.
    """
    fake = FakeEmail()
    await fake.start()
    try:
        uids = [
            fake.add_message(
                "INBOX",
                from_="alice@example.com",
                to=fake.user,
                subject=f"msg {i}",
                body=f"body {i}",
            )
            for i in range(5)
        ]
        client = await _connected_client(fake)
        await client.move_messages(
            "INBOX", [str(u) for u in uids], "Archive",
        )
    finally:
        await fake.stop()

    assert fake.mailboxes["INBOX"].messages == []
    assert len(fake.mailboxes["Archive"].messages) == 5


@pytest.mark.asyncio
async def test_move_messages_silently_skips_unknown_uids() -> None:
    """Per RFC 6851 the server moves whatever UIDs it knows and silently
    skips the rest, returning OK overall. The known UID lands at the
    destination; the unknown ones produce no error.
    """
    fake = FakeEmail()
    await fake.start()
    try:
        real_uid = fake.add_message(
            "INBOX", from_="a@b.com", to=fake.user, subject="real",
        )
        client = await _connected_client(fake)
        await client.move_messages(
            "INBOX", [str(real_uid), "9998", "9999"], "Trash",
        )
    finally:
        await fake.stop()

    assert len(fake.mailboxes["Trash"].messages) == 1


@pytest.mark.asyncio
async def test_move_messages_empty_list_is_noop() -> None:
    """Empty input returns without hitting the wire — saves a server
    round-trip when the agent's filter happened to match nothing."""
    fake = FakeEmail()
    await fake.start()
    try:
        client = await _connected_client(fake)
        await client.move_messages("INBOX", [], "Trash")
    finally:
        await fake.stop()


@pytest.mark.asyncio
async def test_move_messages_rejects_oversize_batch() -> None:
    """The 200-UID cap stays well under typical IMAP command-line
    limits; the client raises ``ValueError`` before sending anything."""
    fake = FakeEmail()
    await fake.start()
    try:
        client = await _connected_client(fake)
        with pytest.raises(ValueError, match="more than 200"):
            await client.move_messages(
                "INBOX", [str(i) for i in range(201)], "Trash",
            )
    finally:
        await fake.stop()


@pytest.mark.asyncio
async def test_move_messages_creates_destination_mailbox_on_fly() -> None:
    """The fake's UID MOVE creates the destination on demand — same shape
    as Gmail/iCloud auto-creating labels. Verifies our client doesn't
    require the dest to exist before the call.
    """
    fake = FakeEmail()
    await fake.start()
    try:
        uid = fake.add_message(
            "INBOX",
            from_="alice@example.com",
            to=fake.user,
            subject="archive me",
        )
        client = await _connected_client(fake)
        await client.move_messages("INBOX", [str(uid)], "Archive/2026")
    finally:
        await fake.stop()

    assert fake.mailboxes["INBOX"].messages == []
    assert "Archive/2026" in fake.mailboxes
    assert len(fake.mailboxes["Archive/2026"].messages) == 1


@pytest.mark.unit
def test_imap_quote_wraps_and_escapes() -> None:
    """The wire-quoting helper produces RFC-3501 quoted strings.

    Plain ASCII names without special chars still get the surrounding
    quotes (callers don't decide; quoting is unconditional). Embedded
    backslash and double-quote get backslash-escaped so iCloud's parser
    doesn't see an unbalanced string.
    """
    from integrations.brokers.email_broker._imap_client import _imap_quote

    assert _imap_quote("INBOX") == '"INBOX"'
    assert _imap_quote("Sent Messages") == '"Sent Messages"'
    assert _imap_quote("[Gmail]/All Mail") == '"[Gmail]/All Mail"'
    # Backslash → \\, double-quote → \"
    assert _imap_quote('weird"name') == '"weird\\"name"'
    assert _imap_quote("with\\backslash") == '"with\\\\backslash"'


@pytest.mark.asyncio
async def test_select_folder_with_space_in_name() -> None:
    """Regression: iCloud / Gmail return ``BAD: Could not parse command``
    when ``SELECT`` is sent with an unquoted multi-token mailbox name
    (Python 3.12 ``imaplib`` does not auto-quote). The fake fixture now
    enforces the same parse rules, so this test would fail without the
    ``_imap_quote`` wrap in ``_ensure_selected``.
    """
    fake = FakeEmail()
    await fake.start()
    try:
        # Seed a folder that exists on real iCloud and trips the bug.
        fake.add_message(
            "Sent Messages", from_=fake.user, to="x@y", subject="hello",
        )
        client = await _connected_client(fake)
        headers = await client.list_messages("Sent Messages", limit=10)
    finally:
        await fake.stop()
    assert len(headers) == 1
    assert headers[0].subject == "hello"


@pytest.mark.asyncio
async def test_move_messages_to_folder_with_space() -> None:
    """Same quoting fix applies to ``UID MOVE``'s destination — moving to
    ``Sent Messages`` (or any iCloud-style multi-word folder) needs the
    destination quoted on the wire.
    """
    fake = FakeEmail()
    await fake.start()
    try:
        uid = fake.add_message(
            "INBOX", from_="a@b.com", to=fake.user, subject="archive me",
        )
        client = await _connected_client(fake)
        await client.move_messages("INBOX", [str(uid)], "Sent Messages")
    finally:
        await fake.stop()
    assert fake.mailboxes["INBOX"].messages == []
    assert len(fake.mailboxes["Sent Messages"].messages) == 1


@pytest.mark.asyncio
async def test_list_messages_returns_empty_for_empty_mailbox() -> None:
    """Regression: iCloud's IMAP returns ``data == [None]`` (not ``[b""]``)
    when ``SEARCH ALL`` matches zero messages, which crashed the parser
    with ``AttributeError: 'NoneType' object has no attribute 'split'``.
    An empty mailbox should return ``[]``, not raise.
    """
    fake = FakeEmail()
    await fake.start()
    try:
        # INBOX is seeded empty by the fixture; no messages added.
        client = await _connected_client(fake)
        headers = await client.list_messages("INBOX", limit=10)
    finally:
        await fake.stop()
    assert headers == []


@pytest.mark.asyncio
async def test_search_messages_returns_empty_when_no_match() -> None:
    """Same ``[None]`` shape applies to ``SEARCH TEXT`` — a query with zero
    matches shouldn't blow up the parser.
    """
    fake = FakeEmail()
    await fake.start()
    try:
        fake.add_message("INBOX", from_="a@b.com", to=fake.user, subject="hi", body="world")
        client = await _connected_client(fake)
        headers = await client.search_messages("INBOX", "nonexistent_unique_token", limit=10)
    finally:
        await fake.stop()
    assert headers == []


@pytest.mark.asyncio
async def test_fetch_message_surfaces_attachment_metadata() -> None:
    """A multipart message with one PDF attachment shows up in the
    ``attachments`` list with the right id, filename, mime, and decoded
    size — not the base64-encoded size on the wire.
    """
    fake = FakeEmail()
    await fake.start()
    payload = b"%PDF-1.4 not really a pdf, but the bytes don't matter here"
    try:
        uid = fake.add_message(
            "INBOX",
            from_="alice@example.com",
            to=fake.user,
            subject="See attached",
            body="Here it is.",
            attachments=[("resume.pdf", "application/pdf", payload)],
        )
        client = await _connected_client(fake)
        message = await client.fetch_message("INBOX", str(uid))
    finally:
        await fake.stop()
    # The body part comes through unchanged.
    assert "Here it is." in message.body_text
    # One attachment with decoded metadata.
    assert len(message.attachments) == 1
    att = message.attachments[0]
    assert att.filename == "resume.pdf"
    assert att.mime_type == "application/pdf"
    assert att.size == len(payload)
    # Attachment id is the IMAP part path — for a multipart with body
    # part (1) and one attachment (2), the attachment is at "2".
    assert att.id == "2"


@pytest.mark.asyncio
async def test_fetch_attachment_returns_bytes_and_filename() -> None:
    """``fetch_attachment`` pulls the named part's bytes back, decoded
    from any Content-Transfer-Encoding (base64 here)."""
    fake = FakeEmail()
    await fake.start()
    payload = b"\x89PNG fake png bytes"
    try:
        uid = fake.add_message(
            "INBOX",
            from_="alice@example.com",
            to=fake.user,
            subject="photo",
            body="see attached",
            attachments=[("photo.png", "image/png", payload)],
        )
        client = await _connected_client(fake)
        bytes_out, filename, mime_type = await client.fetch_attachment(
            "INBOX", str(uid), "2",
        )
    finally:
        await fake.stop()
    assert bytes_out == payload
    assert filename == "photo.png"
    assert mime_type == "image/png"


@pytest.mark.asyncio
async def test_fetch_attachment_unknown_id_raises_lookup_error() -> None:
    """An attachment_id that doesn't match any part raises
    ``LookupError`` so the broker maps it to ``NOT_FOUND`` on the wire.
    """
    fake = FakeEmail()
    await fake.start()
    try:
        uid = fake.add_message(
            "INBOX",
            from_="alice@example.com",
            to=fake.user,
            subject="hi",
            body="no attachments here",
        )
        client = await _connected_client(fake)
        with pytest.raises(LookupError, match="no attachment"):
            await client.fetch_attachment("INBOX", str(uid), "99")
    finally:
        await fake.stop()


# ─────────────────────────────────────────────────────────────────────────
# Reconnect-on-idle-drop coverage.
#
# Real iCloud / Gmail close idle IMAP sockets after ~10–30 minutes; the next
# command tries to ``send()`` over a half-closed TLS connection and ``imaplib``
# raises ``IMAP4.abort``. ``ImapClient`` catches that, re-LOGINs, re-SELECTs
# if the verb cared about a folder, and retries once.
#
# These tests force the failure shape via ``FakeEmail.force_drop_next_imap``
# (the fake closes the next IMAP command's writer, mirroring a server-side
# idle drop) and assert each verb returns the right answer despite the
# transparent reconnect. Coverage is per-verb on purpose: every verb has its
# own ``_op`` closure, and a regression in any one of them would only show
# up on a live connection.
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_mailboxes_recovers_from_idle_drop() -> None:
    """LIST after a forced disconnect: the client reconnects and returns mailboxes."""
    fake = FakeEmail()
    await fake.start()
    try:
        client = await _connected_client(fake)
        fake.force_drop_next_imap = True
        mailboxes = await client.list_mailboxes()
    finally:
        await fake.stop()
    names = sorted(m.name for m in mailboxes)
    assert names == ["INBOX", "Sent", "Trash"]


@pytest.mark.asyncio
async def test_list_messages_recovers_from_idle_drop() -> None:
    """SELECT+SEARCH+FETCH after a forced disconnect: re-LOGIN, re-SELECT, retry."""
    fake = FakeEmail()
    await fake.start()
    try:
        fake.add_message(
            "INBOX",
            from_="alice@example.com",
            to=fake.user,
            subject="post-reconnect hello",
            body="ok",
        )
        client = await _connected_client(fake)
        fake.force_drop_next_imap = True
        headers = await client.list_messages("INBOX", limit=10)
    finally:
        await fake.stop()
    assert len(headers) == 1
    assert headers[0].subject == "post-reconnect hello"


@pytest.mark.asyncio
async def test_search_messages_recovers_from_idle_drop() -> None:
    """SEARCH TEXT after a forced disconnect: same recovery as list_messages."""
    fake = FakeEmail()
    await fake.start()
    try:
        fake.add_message(
            "INBOX",
            from_="alice@example.com",
            to=fake.user,
            subject="needle in haystack",
            body="payload",
        )
        client = await _connected_client(fake)
        fake.force_drop_next_imap = True
        headers = await client.search_messages("INBOX", "needle", limit=10)
    finally:
        await fake.stop()
    assert len(headers) == 1
    assert "needle" in headers[0].subject


@pytest.mark.asyncio
async def test_fetch_message_recovers_from_idle_drop() -> None:
    """UID FETCH after a forced disconnect: re-LOGIN, re-SELECT, refetch full message."""
    fake = FakeEmail()
    await fake.start()
    try:
        uid = fake.add_message(
            "INBOX",
            from_="alice@example.com",
            to=fake.user,
            subject="reconnected fetch",
            body="full body here",
        )
        client = await _connected_client(fake)
        fake.force_drop_next_imap = True
        message = await client.fetch_message("INBOX", str(uid))
    finally:
        await fake.stop()
    assert message.header.subject == "reconnected fetch"
    assert "full body here" in message.body_text


@pytest.mark.asyncio
async def test_fetch_attachment_recovers_from_idle_drop() -> None:
    """``fetch_attachment`` reuses the same path as ``fetch_message`` and must
    recover the same way — exercise it explicitly so the per-verb path stays
    covered if the verbs ever diverge.
    """
    fake = FakeEmail()
    await fake.start()
    payload = b"\x89PNG some bytes"
    try:
        uid = fake.add_message(
            "INBOX",
            from_="alice@example.com",
            to=fake.user,
            subject="photo",
            body="see attached",
            attachments=[("photo.png", "image/png", payload)],
        )
        client = await _connected_client(fake)
        fake.force_drop_next_imap = True
        bytes_out, filename, mime_type = await client.fetch_attachment(
            "INBOX", str(uid), "2",
        )
    finally:
        await fake.stop()
    assert bytes_out == payload
    assert filename == "photo.png"
    assert mime_type == "image/png"


@pytest.mark.asyncio
async def test_move_messages_recovers_from_idle_drop() -> None:
    """UID MOVE after a forced disconnect: source ends empty, dest has the message."""
    fake = FakeEmail()
    await fake.start()
    try:
        uid = fake.add_message(
            "INBOX", from_="a@b.com", to=fake.user, subject="bye",
        )
        client = await _connected_client(fake)
        fake.force_drop_next_imap = True
        await client.move_messages("INBOX", [str(uid)], "Trash")
    finally:
        await fake.stop()
    assert fake.mailboxes["INBOX"].messages == []
    assert len(fake.mailboxes["Trash"].messages) == 1


@pytest.mark.asyncio
async def test_reconnect_clears_cached_selection_so_next_call_re_selects() -> None:
    """Regression guard for the cached-mailbox state machine.

    ``_current_mailbox`` is a cache that lets consecutive ops on the same
    folder skip a SELECT round-trip. After ``_with_reconnect`` reconnects,
    the cache must reset to ``None`` — otherwise the retry's
    ``_select_in_thread`` short-circuits on the cached name and skips SELECT
    on the *new* connection, leaving SEARCH/FETCH to run against a freshly-
    LOGIN'd-but-not-SELECTed handle (server replies ``BAD: Must SELECT first``).

    The bug only manifests when the retry asks for the **same** folder that
    was cached pre-drop — a different folder always falls through the
    cache check on its own. So this test:

      1. Primes the cache on INBOX via a successful list_messages
      2. Forces a drop on the next command (the SEARCH inside the second
         list_messages call, since the cached SELECT is skipped)
      3. Asks for INBOX *again* — if the cache wasn't cleared on reconnect,
         the retry skips SELECT and SEARCH fails with BAD on the new conn.
    """
    fake = FakeEmail()
    await fake.start()
    try:
        fake.add_message(
            "INBOX", from_="a@b.com", to=fake.user, subject="msg",
        )
        client = await _connected_client(fake)
        # Prime the selection cache on INBOX.
        first = await client.list_messages("INBOX", limit=10)
        assert len(first) == 1 and first[0].subject == "msg"
        # Force a drop on the next command. Since INBOX is already cached,
        # _select_in_thread short-circuits and the drop hits SEARCH —
        # exactly the path where forgetting to clear the cache on reconnect
        # would let the retry skip SELECT against the new connection.
        fake.force_drop_next_imap = True
        second = await client.list_messages("INBOX", limit=10)
    finally:
        await fake.stop()
    assert len(second) == 1
    assert second[0].subject == "msg"


