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
