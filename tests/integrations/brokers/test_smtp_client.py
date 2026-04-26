"""Tests for ``brokers/email_broker/_smtp_client.py`` against ``fake_email``.

Same shape as ``test_imap_client.py``: a real ``FakeEmail`` SMTP server on a
random port, plain TCP (no STARTTLS — the fake doesn't speak it), and the
real ``SmtpClient`` driving it. If either side is wrong the test fails.

We pass ``starttls=False`` because the fake speaks plaintext SMTP. Production
brokers default to ``starttls=True`` (port 587 submission flow); the production
path is exercised by the end-to-end broker subprocess tests that point a real
broker at the fake with ``SMTP_STARTTLS=false`` env.
"""

from __future__ import annotations

import email as _email

import pytest

from integrations.brokers.email_broker._smtp_client import SmtpAuthError, SmtpClient
from tests.integrations.fixtures.fake_email import FakeEmail


@pytest.mark.asyncio
async def test_connect_and_send_message_lands_in_outbox() -> None:
    """Happy path: connect succeeds, send_message delivers the body to the
    fake's outbox with the right envelope addresses.
    """
    fake = FakeEmail()
    await fake.start()
    try:
        client = SmtpClient(
            host=fake.smtp_host,
            port=fake.smtp_port,
            user=fake.user,
            password=fake.password,
            starttls=False,
        )
        await client.connect()
        message_id = await client.send_message(
            to=["alice@example.com"],
            subject="hello",
            body="this is the body",
        )
    finally:
        await fake.stop()

    assert len(fake.outbox) == 1
    received = fake.outbox[0]
    assert received.mail_from == fake.user
    assert received.rcpt_to == ["alice@example.com"]
    parsed = _email.message_from_bytes(received.raw)
    assert parsed["Subject"] == "hello"
    assert parsed["From"] == fake.user
    assert parsed["To"] == "alice@example.com"
    # Message-ID returned to the caller matches the one in the wire bytes —
    # callers correlate sends with later IMAP fetches via this id.
    assert parsed["Message-ID"] == message_id
    assert message_id  # non-empty
    assert "this is the body" in parsed.get_payload()


@pytest.mark.asyncio
async def test_send_message_with_multiple_recipients_lists_all_in_envelope() -> None:
    """``to`` array of N addresses produces N RCPT TOs and a comma-joined
    ``To:`` header. The fake captures the envelope separately from headers,
    so we can verify both shapes.
    """
    fake = FakeEmail()
    await fake.start()
    try:
        client = SmtpClient(
            host=fake.smtp_host,
            port=fake.smtp_port,
            user=fake.user,
            password=fake.password,
            starttls=False,
        )
        await client.connect()
        await client.send_message(
            to=["alice@example.com", "bob@example.com"],
            subject="ping",
            body="hi",
        )
    finally:
        await fake.stop()

    received = fake.outbox[0]
    assert received.rcpt_to == ["alice@example.com", "bob@example.com"]
    parsed = _email.message_from_bytes(received.raw)
    assert parsed["To"] == "alice@example.com, bob@example.com"


@pytest.mark.asyncio
async def test_connect_raises_smtp_auth_error_when_auth_rejected() -> None:
    """Persistent AUTH rejection raises ``SmtpAuthError``, the sentinel the
    broker's ``__main__`` maps to ``sys.exit(77)`` so the supervisor flips
    the integration to ``auth_failed``.
    """
    fake = FakeEmail()
    await fake.start()
    try:
        fake.reject_next_n_smtp_auths = 1
        client = SmtpClient(
            host=fake.smtp_host,
            port=fake.smtp_port,
            user=fake.user,
            password="wrong",
            starttls=False,
        )
        with pytest.raises(SmtpAuthError):
            await client.connect()
    finally:
        await fake.stop()


@pytest.mark.asyncio
async def test_send_message_reconnects_after_dropped_session() -> None:
    """Idle timeout / proxy drop → the first ``send_message`` reconnects
    transparently. Without the reconnect, callers would have to write
    retry boilerplate around every send. We simulate a drop by closing
    the underlying smtplib connection out from under the client.
    """
    fake = FakeEmail()
    await fake.start()
    try:
        client = SmtpClient(
            host=fake.smtp_host,
            port=fake.smtp_port,
            user=fake.user,
            password=fake.password,
            starttls=False,
        )
        await client.connect()

        # First send establishes baseline.
        await client.send_message(
            to=["alice@example.com"], subject="one", body="x",
        )
        assert len(fake.outbox) == 1

        # Simulate a dead session: close the smtplib socket so the next
        # send raises SMTPServerDisconnected, exercising the reconnect path.
        # The private attribute access is deliberate — there's no public
        # "force-disconnect" knob, and the whole point of the test is to
        # poke at this internal state.
        assert client._smtp is not None
        client._smtp.close()

        # Reconnect path should rebuild the session and succeed.
        await client.send_message(
            to=["bob@example.com"], subject="two", body="y",
        )
    finally:
        await fake.stop()

    assert len(fake.outbox) == 2
    assert fake.outbox[1].rcpt_to == ["bob@example.com"]
