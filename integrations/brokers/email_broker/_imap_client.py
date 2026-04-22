"""IMAP client for the email broker.

A thin async wrapper around stdlib ``imaplib``. ``imaplib`` is synchronous and
not thread-safe; two mechanics make it work inside an asyncio broker:

- Every blocking IMAP call runs via ``asyncio.to_thread``, so the event loop
  stays responsive while a SEARCH or FETCH is in flight.
- An ``asyncio.Lock`` serializes access to the single underlying IMAP session.
  IMAP is stateful — ``SELECT <mailbox>`` locks the session to one mailbox at
  a time — so concurrent callers on different mailboxes would trip over each
  other's selected state. The lock also caches the currently-selected mailbox
  so consecutive operations on the same one skip redundant SELECT round-trips.

The client holds the credential in memory for the lifetime of the broker so it
can reconnect transparently on idle-timeout / drop. The broker's ``__main__``
wipes the credential from ``os.environ`` after handing it here; the private
attribute on this class is the only live reference for the rest of the process.
"""

from __future__ import annotations

import asyncio
import imaplib
import logging

from integrations.brokers.email_broker.types import Mailbox

logger = logging.getLogger(__name__)


class ImapAuthError(Exception):
    """IMAP LOGIN was rejected. The broker's entry code maps this to exit(77)."""


class ImapClient:
    """Single IMAP session shared by all concurrent verb calls in this broker.

    ("Session" here refers to the RFC-3501 IMAP session state — the TCP
    connection plus the currently-SELECTed mailbox. One ``ImapClient`` owns
    exactly one such session for the broker's lifetime.)
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        *,
        use_tls: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        # The only live reference to the cred after broker bootstrap. Stays on the
        # instance so we can re-LOGIN after a transparent reconnect.
        self._password = password
        self._use_tls = use_tls

        self._lock = asyncio.Lock()
        self._imap: imaplib.IMAP4 | None = None
        self._current_mailbox: str | None = None

    async def connect(self) -> None:
        """Open the IMAP connection and authenticate.

        Raises ``ImapAuthError`` if the server rejects LOGIN — the broker's
        entry code translates that into ``sys.exit(77)`` so the supervisor
        flips state to ``auth_failed``.
        """
        def _blocking_connect() -> imaplib.IMAP4:
            # IMAP4_SSL for implicit TLS (port 993); IMAP4 for plaintext (test fakes
            # on random ports, or legacy StartTLS setups which we don't support in v1).
            conn: imaplib.IMAP4
            if self._use_tls:
                conn = imaplib.IMAP4_SSL(self._host, self._port)
            else:
                conn = imaplib.IMAP4(self._host, self._port)
            typ, data = conn.login(self._user, self._password)
            if typ != "OK":
                # imaplib already raised imaplib.IMAP4.error on most LOGIN rejections;
                # this branch catches the rarer "OK-but-not-really" server responses.
                msg = f"IMAP LOGIN returned {typ}: {data!r}"
                raise ImapAuthError(msg)
            return conn

        try:
            self._imap = await asyncio.to_thread(_blocking_connect)
        except imaplib.IMAP4.error as exc:
            # imaplib raises its own exception type on AUTHENTICATIONFAILED etc.
            # Translate to our sentinel so the broker can distinguish auth-fail
            # (exit 77) from other network errors (exit 1).
            msg = f"IMAP LOGIN rejected: {exc}"
            raise ImapAuthError(msg) from exc
        logger.info("IMAP LOGIN ok (%s@%s:%d)", self._user, self._host, self._port)

    async def list_mailboxes(self) -> list[Mailbox]:
        """Return every mailbox on the server.

        Representative of the read-verb pattern: acquire the lock, run the blocking
        IMAP call in a worker thread, parse the response into typed domain models.
        """
        async with self._lock:
            if self._imap is None:
                # TODO: reconnect path goes here when we add drop-handling; for now
                # connect() must have been awaited by broker bootstrap first.
                msg = "ImapClient used before connect()"
                raise RuntimeError(msg)

            # Capture the narrowed reference into a local. The inner ``_blocking_list``
            # closes over ``conn`` rather than ``self._imap``; that keeps the type
            # checker happy without a runtime ``assert`` (which ``python -O`` would
            # strip) and documents that only the IMAP handle — not the whole session —
            # crosses into the worker thread.
            conn = self._imap

            def _blocking_list() -> list[bytes]:
                typ, data = conn.list()
                if typ != "OK":
                    msg = f"LIST failed: {typ} {data!r}"
                    raise RuntimeError(msg)
                # imaplib returns data as a list of bytes lines, each like:
                #   b'(\\HasNoChildren) "/" "INBOX"'
                return [line for line in data if isinstance(line, bytes)]

            raw_lines = await asyncio.to_thread(_blocking_list)

        return [_parse_list_line(line) for line in raw_lines]


def _parse_list_line(line: bytes) -> Mailbox:
    r"""Parse one line of ``IMAP LIST`` output into a :class:`Mailbox`.

    Wire shape (RFC 3501): ``(\HasNoChildren \Marked) "/" "INBOX"`` — a
    paren-wrapped flag list, a quoted delimiter, then a quoted mailbox name.
    We only care about the flags and the name; the delimiter is an IMAP detail
    the upper layers don't need.
    """
    text = line.decode("utf-8", errors="replace")
    # Flags are the first parenthesized group. Everything we need fits a single
    # regex-free pass, which is easier to debug than imaplib's built-in parser.
    attrs_end = text.find(")")
    attrs_text = text[1:attrs_end] if attrs_end > 0 else ""
    attrs = [a for a in attrs_text.split() if a]

    # Last quoted string on the line is the mailbox name. Scan from the right
    # so we don't confuse it with the (quoted) delimiter.
    name = ""
    last_quote = text.rfind('"')
    if last_quote > 0:
        prev_quote = text.rfind('"', 0, last_quote)
        if prev_quote >= 0:
            name = text[prev_quote + 1 : last_quote]

    return Mailbox(name=name, attrs=attrs)
