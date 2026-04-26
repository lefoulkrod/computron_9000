"""SMTP client for the email broker.

Thin async wrapper around stdlib :mod:`smtplib`. Mirrors the IMAP client's
contract:

- Every blocking call runs through ``asyncio.to_thread`` so the event loop
  stays responsive while a connection / handshake / send is in flight.
- An ``asyncio.Lock`` serializes access to the underlying ``smtplib.SMTP``
  session — ``smtplib`` is synchronous and not thread-safe, and SMTP itself
  serializes one transaction at a time per connection.

Connection lifecycle: we open one SMTP session at ``connect()`` time and
hold it open for the broker's lifetime. ``send_message`` reconnects
transparently on a dropped session — STARTTLS providers occasionally idle
us out after a few minutes, and a stale connection is the normal failure
shape, not a fatal one.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

logger = logging.getLogger(__name__)


class SmtpAuthError(Exception):
    """SMTP AUTH was rejected. The broker's entry code maps this to exit(77)."""


class SmtpClient:
    """Single SMTP session shared by all concurrent verb calls in this broker."""

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        *,
        starttls: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        # Same hygiene rationale as ImapClient: held for the broker's lifetime
        # so we can reconnect transparently after an idle timeout.
        self._password = password
        self._starttls = starttls

        self._lock = asyncio.Lock()
        self._smtp: smtplib.SMTP | None = None

    async def connect(self) -> None:
        """Open the SMTP session and authenticate.

        Raises :class:`SmtpAuthError` if the server rejects AUTH — the
        broker's entry code translates that into ``sys.exit(77)``.
        """
        try:
            self._smtp = await asyncio.to_thread(self._blocking_connect)
        except smtplib.SMTPAuthenticationError as exc:
            msg = f"SMTP AUTH rejected: {exc}"
            raise SmtpAuthError(msg) from exc
        logger.info("SMTP AUTH ok (%s@%s:%d)", self._user, self._host, self._port)

    def _blocking_connect(self) -> smtplib.SMTP:
        """Synchronous connect — runs inside a worker thread.

        Used both by ``connect()`` and as the reconnect path inside
        ``send_message``, so it lives on the instance rather than as a
        local closure.
        """
        conn = smtplib.SMTP(self._host, self._port, timeout=30)
        conn.ehlo()
        if self._starttls:
            # 587-style submission: STARTTLS upgrade after the unencrypted
            # banner. Re-EHLO afterward is required by RFC 3207 — capabilities
            # advertised before TLS may differ from those after.
            conn.starttls()
            conn.ehlo()
        conn.login(self._user, self._password)
        return conn

    async def send_message(
        self,
        *,
        to: list[str],
        subject: str,
        body: str,
    ) -> str:
        """Send a plain-text message; return the ``Message-ID`` header.

        ``to`` is a list of bare addresses. We attach a generated
        ``Message-ID`` and return it so callers can correlate the send with
        later IMAP fetches from the Sent folder.
        """
        async with self._lock:
            msg = EmailMessage()
            msg["From"] = self._user
            msg["To"] = ", ".join(to)
            msg["Subject"] = subject
            message_id = make_msgid(domain=self._user.split("@", 1)[-1] or "localhost")
            msg["Message-ID"] = message_id
            msg.set_content(body)

            def _blocking_send() -> None:
                conn = self._smtp
                if conn is None:
                    conn = self._blocking_connect()
                    self._smtp = conn
                try:
                    conn.send_message(msg, from_addr=self._user, to_addrs=list(to))
                except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError):
                    # Idle drop is the normal shape — reconnect once and retry.
                    # Anything beyond that is a real failure; let it bubble.
                    conn = self._blocking_connect()
                    self._smtp = conn
                    conn.send_message(msg, from_addr=self._user, to_addrs=list(to))

            await asyncio.to_thread(_blocking_send)
        return message_id
