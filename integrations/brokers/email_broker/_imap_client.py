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
import email as _email
import email.header
import email.utils
import imaplib
import logging
import re

import html2text

from integrations.brokers.email_broker.types import Attachment, Mailbox, Message, MessageHeader

logger = logging.getLogger(__name__)

# Header fields we ask the IMAP server for when listing or searching.
_HEADER_FIELDS = "FROM TO SUBJECT DATE"

# Email-specific HTML→Markdown rendering. Tuned for what the agent wants out
# of an email body: real paragraphs, real links, no image data-URIs, no
# fragment anchors.
_html2md = html2text.HTML2Text()
_html2md.body_width = 0  # no hard-wrap; let paragraphs flow
_html2md.ignore_images = True  # alt text only, never [![...](data:...)]
_html2md.unicode_snob = True  # real unicode chars, not &amp; / &nbsp;
_html2md.protect_links = True  # don't auto-shorten or rewrap link URLs
_html2md.skip_internal_links = True  # in-page anchors are noise in email


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
        try:
            self._imap = await asyncio.to_thread(self._blocking_connect)
        except imaplib.IMAP4.error as exc:
            # imaplib raises its own exception type on AUTHENTICATIONFAILED etc.
            # Translate to our sentinel so the broker can distinguish auth-fail
            # (exit 77) from other network errors (exit 1).
            msg = f"IMAP LOGIN rejected: {exc}"
            raise ImapAuthError(msg) from exc
        logger.info("IMAP LOGIN ok (%s@%s:%d)", self._user, self._host, self._port)

    def _blocking_connect(self) -> imaplib.IMAP4:
        """Synchronous connect — runs inside a worker thread.

        Used by ``connect()`` and as the reconnect path inside
        ``_with_reconnect``, so it lives on the instance rather than a
        local closure.
        """
        # IMAP4_SSL for implicit TLS (port 993); IMAP4 for plaintext (test fakes
        # on random ports, or legacy StartTLS setups which we don't support in v1).
        # 120s socket timeout applies to every blocking op (connect, login, FETCH,
        # SEARCH); without it a half-open socket pins the broker's asyncio.Lock
        # until OS keepalive breaks the connection minutes later. Matches
        # SmtpClient — same rationale for slow upstreams (iCloud).
        conn: imaplib.IMAP4
        if self._use_tls:
            conn = imaplib.IMAP4_SSL(self._host, self._port, timeout=120)
        else:
            conn = imaplib.IMAP4(self._host, self._port, timeout=120)
        typ, data = conn.login(self._user, self._password)
        if typ != "OK":
            # imaplib already raised imaplib.IMAP4.error on most LOGIN rejections;
            # this branch catches the rarer "OK-but-not-really" server responses.
            msg = f"IMAP LOGIN returned {typ}: {data!r}"
            raise ImapAuthError(msg)
        return conn

    def _with_reconnect(self, op):
        """Run ``op(conn)`` synchronously; reconnect+retry once on stale-conn errors.

        Caller must hold ``self._lock`` and must have awaited ``connect()``
        first. ``imaplib`` wraps socket-level failures (idle drop, RST,
        unsolicited BYE) as ``IMAP4.abort`` — we tear the dead handle
        down, re-LOGIN, and retry once. A second failure propagates.

        ``IMAP4.error`` (the parent class) is *not* caught: it also fires
        on real ``BAD``/``NO`` responses where the connection is healthy
        and retrying would loop on a genuine protocol bug.
        """
        conn = self._imap
        if conn is None:
            msg = "ImapClient used before connect()"
            raise RuntimeError(msg)
        try:
            return op(conn)
        except imaplib.IMAP4.abort as exc:
            logger.info("IMAP connection stale (%s); reconnecting and retrying once", exc)
            try:
                conn.shutdown()
            except Exception:  # noqa: BLE001
                pass
            self._current_mailbox = None
            conn = self._blocking_connect()
            self._imap = conn
            return op(conn)

    def _select_in_thread(self, conn: imaplib.IMAP4, folder: str) -> None:
        """Issue SELECT inside the worker thread, caching the selection.

        No-op if ``folder`` is already selected. ``_with_reconnect`` clears
        ``_current_mailbox`` after a reconnect so the retry pass re-SELECTs
        against the fresh connection.

        Quote the folder — Python 3.12 ``imaplib`` doesn't auto-quote, so a
        name with a space (``Sent Messages``, ``[Gmail]/All Mail``) reaches
        the server as two tokens and gets ``BAD: Could not parse command``.
        """
        if self._current_mailbox == folder:
            return
        typ, data = conn.select(_imap_quote(folder))
        if typ != "OK":
            msg = f"SELECT {folder!r} failed: {typ} {data!r}"
            raise RuntimeError(msg)
        self._current_mailbox = folder

    async def list_mailboxes(self) -> list[Mailbox]:
        """Return every mailbox on the server.

        Representative of the read-verb pattern: acquire the lock, run the blocking
        IMAP call in a worker thread, parse the response into typed domain models.
        """
        async with self._lock:

            def _op(conn: imaplib.IMAP4) -> list[bytes]:
                typ, data = conn.list()
                if typ != "OK":
                    msg = f"LIST failed: {typ} {data!r}"
                    raise RuntimeError(msg)
                # imaplib returns data as a list of bytes lines, each like:
                #   b'(\\HasNoChildren) "/" "INBOX"'
                return [line for line in data if isinstance(line, bytes)]

            raw_lines = await asyncio.to_thread(self._with_reconnect, _op)

        return [_parse_list_line(line) for line in raw_lines]

    async def list_messages(self, folder: str, limit: int) -> list[MessageHeader]:
        """Return the most recent ``limit`` message headers in ``folder``.

        Ordering is newest-first (highest sequence number = most recently
        appended). The caller sees a list small enough to display directly.
        """
        limit = max(1, min(limit, 200))  # hard cap — protect context budget
        async with self._lock:

            def _op(conn: imaplib.IMAP4) -> list[tuple[str, bytes]]:
                self._select_in_thread(conn, folder)
                # SEARCH ALL — return every message's *sequence number* in the
                # selected mailbox. Sequence numbers are 1..N positions that
                # change as messages get added/deleted; the FETCH below also
                # asks for UID so the caller gets a stable id back.
                typ, data = conn.search(None, "ALL")
                if typ != "OK":
                    msg = f"SEARCH ALL failed: {typ} {data!r}"
                    raise RuntimeError(msg)
                # An empty mailbox can come back as ``data == [None]``
                # rather than ``[b""]`` on some servers (notably iCloud);
                # treat both shapes as zero hits.
                if not data or data[0] is None:
                    return []
                seq_ids = data[0].split()
                if not seq_ids:
                    return []
                # Highest sequence numbers are the most recently appended,
                # so the tail is the newest N messages.
                tail = seq_ids[-limit:]
                seq_set = b",".join(tail).decode("ascii")
                # FETCH — pull message parts for the given sequence range.
                #   UID                                   → include the stable id
                #   BODY.PEEK[HEADER.FIELDS (FROM TO ..)] → just those headers,
                #     PEEK so the message isn't marked \Seen as a side effect.
                typ, uid_data = conn.fetch(
                    seq_set,
                    f"(UID BODY.PEEK[HEADER.FIELDS ({_HEADER_FIELDS})])",
                )
                if typ != "OK":
                    msg = f"FETCH headers failed: {typ} {uid_data!r}"
                    raise RuntimeError(msg)
                return _collect_fetch_pairs(uid_data)

            raw = await asyncio.to_thread(self._with_reconnect, _op)

        return [_parse_header_hit(uid, blob, folder) for uid, blob in reversed(raw)]

    async def search_messages(
        self,
        folder: str,
        query: str,
        limit: int,
    ) -> list[MessageHeader]:
        """Run IMAP ``SEARCH TEXT`` in ``folder``, return matched headers.

        IMAP's ``TEXT`` criterion matches both headers and body. Single-folder
        only — there's no standard cross-folder search in IMAP.
        """
        limit = max(1, min(limit, 200))
        # Quote for the IMAP wire. The quoted form can't hold embedded
        # double-quotes or backslashes, so we strip them — good enough for
        # natural-language search and avoids building a literal command.
        safe_query = query.replace("\\", "").replace('"', "")
        async with self._lock:

            def _op(conn: imaplib.IMAP4) -> list[tuple[str, bytes]]:
                self._select_in_thread(conn, folder)
                # SEARCH TEXT "query" — match the query against headers and
                # body in the selected mailbox. IMAP has no cross-mailbox
                # search; callers iterate folders client-side if they need
                # broader coverage. Returns sequence numbers, same as
                # SEARCH ALL above.
                typ, data = conn.search(None, "TEXT", f'"{safe_query}"')
                if typ != "OK":
                    msg = f"SEARCH TEXT failed: {typ} {data!r}"
                    raise RuntimeError(msg)
                # Same iCloud-style ``[None]`` no-match shape as in
                # ``list_messages`` — defend against it here too.
                if not data or data[0] is None:
                    return []
                seq_ids = data[0].split()
                if not seq_ids:
                    return []
                tail = seq_ids[-limit:]
                seq_set = b",".join(tail).decode("ascii")
                # Same FETCH shape as list_messages — UID + selected
                # header fields, PEEK to avoid marking \Seen.
                typ, hdr_data = conn.fetch(
                    seq_set,
                    f"(UID BODY.PEEK[HEADER.FIELDS ({_HEADER_FIELDS})])",
                )
                if typ != "OK":
                    msg = f"FETCH headers failed: {typ} {hdr_data!r}"
                    raise RuntimeError(msg)
                return _collect_fetch_pairs(hdr_data)

            raw = await asyncio.to_thread(self._with_reconnect, _op)

        return [_parse_header_hit(uid, blob, folder) for uid, blob in reversed(raw)]

    async def fetch_message(self, folder: str, uid: str) -> Message:
        """Fetch one full message by ``uid`` in ``folder``.

        Raises ``LookupError`` if the UID is unknown in the current mailbox.
        """
        async with self._lock:

            def _op(conn: imaplib.IMAP4) -> bytes:
                self._select_in_thread(conn, folder)
                # UID FETCH — like FETCH but the id is the stable UID instead
                # of the volatile sequence number. ``BODY.PEEK[]`` (no section
                # path) means "the whole RFC 822 message, raw" — headers and
                # body together, as one byte blob the email parser can chew on.
                # PEEK keeps the \Seen flag untouched.
                typ, data = conn.uid("FETCH", uid, "(BODY.PEEK[])")
                if typ != "OK":
                    msg = f"UID FETCH failed: {typ} {data!r}"
                    raise RuntimeError(msg)
                for part in data:
                    if isinstance(part, tuple) and len(part) >= 2:
                        return part[1]
                raise LookupError(f"no such message: uid={uid}")

            raw = await asyncio.to_thread(self._with_reconnect, _op)

        msg = _email.message_from_bytes(raw)
        header = MessageHeader(
            uid=uid,
            folder=folder,
            from_=_decode_header(msg.get("From", "")),
            to=_decode_header(msg.get("To", "")),
            subject=_decode_header(msg.get("Subject", "")),
            date=_normalize_date(msg.get("Date", "")),
        )
        return Message(
            header=header,
            body_text=_extract_body_text(msg),
            attachments=_extract_attachments(msg),
        )

    async def fetch_attachment(
        self, folder: str, uid: str, attachment_id: str,
    ) -> tuple[bytes, str, str]:
        """Fetch one attachment's bytes by IMAP part path.

        Returns ``(payload_bytes, filename, mime_type)``. The bytes are
        already decoded from any Content-Transfer-Encoding (base64, qp,
        etc.) so callers can write them straight to disk.

        For walking-skeleton scope this re-fetches the full message and
        extracts the named part client-side. A future optimization could
        use IMAP partial fetch (``BODY.PEEK[N]``) to pull just the part —
        worth doing once we hit attachments large enough that the full-
        message round-trip is the bottleneck.

        Raises ``LookupError`` if the UID isn't in the mailbox or the
        ``attachment_id`` doesn't match any part in the message.
        """
        async with self._lock:

            def _op(conn: imaplib.IMAP4) -> bytes:
                self._select_in_thread(conn, folder)
                typ, data = conn.uid("FETCH", uid, "(BODY.PEEK[])")
                if typ != "OK":
                    msg = f"UID FETCH failed: {typ} {data!r}"
                    raise RuntimeError(msg)
                for part in data:
                    if isinstance(part, tuple) and len(part) >= 2:
                        return part[1]
                raise LookupError(f"no such message: uid={uid}")

            raw = await asyncio.to_thread(self._with_reconnect, _op)

        msg = _email.message_from_bytes(raw)
        for part_path, part in _walk_with_paths(msg):
            if part_path != attachment_id:
                continue
            payload = part.get_payload(decode=True) or b""
            if not isinstance(payload, bytes):
                payload = b""
            filename = part.get_filename() or ""
            return payload, filename, part.get_content_type()
        raise LookupError(
            f"no attachment {attachment_id!r} in uid={uid}",
        )

    async def move_messages(
        self, folder: str, uids: list[str], dest_folder: str,
    ) -> None:
        """Move ``uids`` from ``folder`` to ``dest_folder`` in one round-trip.

        Uses IMAP UID MOVE (RFC 6851) with a comma-joined UID set, which
        iCloud and Gmail both support. UIDs the server doesn't recognize
        are silently skipped (server behavior); the wire response is just
        ``OK`` either way, so the only thing the caller learns is that
        the command was accepted. Callers needing exact accounting must
        re-list the source folder.

        Capped at 200 UIDs per call to stay well under server line-length
        limits. The verb layer rejects oversize batches before we get here.

        Raises ``LookupError`` if the destination doesn't exist or the
        whole command fails.
        """
        if not uids:
            return
        if len(uids) > 200:
            msg = f"cannot move more than 200 messages per call (got {len(uids)})"
            raise ValueError(msg)
        uid_set = ",".join(uids)
        async with self._lock:

            def _op(conn: imaplib.IMAP4) -> None:
                self._select_in_thread(conn, folder)
                # imaplib doesn't expose a typed ``move`` helper, so we drive
                # the raw UID MOVE command. Quote the destination — same
                # Python-3.12-imaplib reason as in ``_select_in_thread``:
                # a name with a space gets parsed as extra args otherwise.
                typ, data = conn.uid("MOVE", uid_set, _imap_quote(dest_folder))
                if typ != "OK":
                    detail = b" ".join(d for d in data if isinstance(d, bytes))
                    text = detail.decode("utf-8", errors="replace")
                    # NO usually means "no such mailbox"; the broker maps
                    # LookupError to NOT_FOUND on the wire.
                    msg = (
                        f"UID MOVE uids={uid_set} -> {dest_folder!r} "
                        f"failed: {typ} {text!r}"
                    )
                    raise LookupError(msg)

            await asyncio.to_thread(self._with_reconnect, _op)


def _imap_quote(name: str) -> str:
    r"""Wrap an IMAP command argument in a quoted string for the wire.

    Python 3.12's ``imaplib`` does not auto-quote command arguments — it
    just concatenates them with spaces. A folder name like ``Sent Messages``
    therefore reaches the server as two tokens, and the server replies
    ``BAD: Could not parse command``. We quote ourselves: ``Sent Messages``
    becomes ``"Sent Messages"`` on the wire.

    Embedded ``\`` and ``"`` are backslash-escaped per RFC 3501 quoted
    strings. Names with non-ASCII codepoints would technically need IMAP
    modified UTF-7 (RFC 3501 § 5.1.3), but every catalog provider we
    support today exposes only ASCII folder names, so we don't transcode.
    """
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


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


_UID_RE = re.compile(rb"UID (\d+)")


def _collect_fetch_pairs(data: list) -> list[tuple[str, bytes]]:
    """Extract ``(uid, raw_bytes)`` pairs from an ``imaplib.IMAP4.fetch`` response.

    imaplib returns a list where each FETCH hit is a 2-tuple
    ``(b"N (UID X BODY[HEADER.FIELDS ...] {len}", b"<raw>")`` optionally
    followed by a closing ``b")"`` bytestring. We pull the UID out of the
    preamble and pair it with the raw bytes.
    """
    pairs: list[tuple[str, bytes]] = []
    for item in data:
        if not isinstance(item, tuple) or len(item) < 2:
            continue
        preamble, raw = item[0], item[1]
        if not isinstance(preamble, bytes) or not isinstance(raw, bytes):
            continue
        m = _UID_RE.search(preamble)
        if m is None:
            continue
        pairs.append((m.group(1).decode("ascii"), raw))
    return pairs


def _parse_header_hit(uid: str, raw: bytes, folder: str) -> MessageHeader:
    """Parse a raw RFC 822 header blob into a :class:`MessageHeader`."""
    msg = _email.message_from_bytes(raw)
    return MessageHeader(
        uid=uid,
        folder=folder,
        from_=_decode_header(msg.get("From", "")),
        to=_decode_header(msg.get("To", "")),
        subject=_decode_header(msg.get("Subject", "")),
        date=_normalize_date(msg.get("Date", "")),
    )


def _decode_header(value: str) -> str:
    """Decode an RFC 2047 encoded-word header into a plain unicode string."""
    if not value:
        return ""
    parts = email.header.decode_header(value)
    out: list[str] = []
    for text, charset in parts:
        if isinstance(text, bytes):
            try:
                out.append(text.decode(charset or "utf-8", errors="replace"))
            except LookupError:
                out.append(text.decode("utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out).strip()


def _normalize_date(value: str) -> str:
    """Return an ISO-8601 timestamp, or the original string if unparseable.

    ``parsedate_to_datetime`` raises ``ValueError`` (3.10+) on garbage input
    and ``TypeError`` on the empty 9-tuple some servers return — in both
    cases we'd rather show the agent the raw header than drop the field.
    """
    if not value:
        return ""
    try:
        dt = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return value
    if dt is None:
        return value
    return dt.isoformat()


def _walk_with_paths(
    msg: _email.message.Message, prefix: str = "",
) -> list[tuple[str, _email.message.Message]]:
    """Yield ``(imap_part_path, part)`` for every leaf part in ``msg``.

    Numbering matches RFC 3501 BODYSTRUCTURE: a non-multipart message is
    a single part numbered ``"1"``; a top-level multipart's children are
    ``"1"``, ``"2"``, …; nested multiparts dot-extend (``"2.1"``,
    ``"2.2"``). Only leaves are yielded — multipart container nodes
    aren't addressable as content on their own.
    """
    out: list[tuple[str, _email.message.Message]] = []
    if not msg.is_multipart():
        # Non-multipart top-level message: addressable as part "1".
        out.append((prefix or "1", msg))
        return out
    children = msg.get_payload()
    if not isinstance(children, list):
        return out
    for index, child in enumerate(children, start=1):
        child_path = f"{prefix}.{index}" if prefix else str(index)
        if child.is_multipart():
            out.extend(_walk_with_paths(child, prefix=child_path))
        else:
            out.append((child_path, child))
    return out


def _extract_attachments(msg: _email.message.Message) -> list[Attachment]:
    """Return :class:`Attachment` records for every part with a filename.

    A "filename" comes from either ``Content-Disposition: attachment;
    filename=...`` or the ``name=`` parameter of ``Content-Type`` —
    Python's ``email.Message.get_filename`` covers both. Parts without a
    filename (the body's text/plain or text/html alternatives, inline
    images that aren't given names) are not surfaced as attachments.
    """
    out: list[Attachment] = []
    for part_path, part in _walk_with_paths(msg):
        filename = part.get_filename()
        if not filename:
            continue
        payload = part.get_payload(decode=True)
        size = len(payload) if isinstance(payload, bytes) else 0
        out.append(
            Attachment(
                id=part_path,
                filename=filename,
                mime_type=part.get_content_type(),
                size=size,
            ),
        )
    return out


def _extract_body_text(msg: _email.message.Message) -> str:
    """Best-effort text rendering of a possibly-multipart message.

    Prefers ``text/plain`` parts; falls back to a Markdown rendering of
    ``text/html`` when the message is HTML-only. Never raises — on exotic
    encodings it returns whatever decodes, or an empty string.
    """
    if msg.is_multipart():
        plain = _find_part(msg, "text/plain")
        if plain is not None:
            return _decode_part_payload(plain)
        html = _find_part(msg, "text/html")
        if html is not None:
            return _html_to_markdown(_decode_part_payload(html))
        return ""
    content_type = msg.get_content_type()
    payload = _decode_part_payload(msg)
    if content_type == "text/html":
        return _html_to_markdown(payload)
    return payload


def _find_part(msg: _email.message.Message, content_type: str) -> _email.message.Message | None:
    for part in msg.walk():
        if part.get_content_type() == content_type and not part.is_multipart():
            return part
    return None


def _decode_part_payload(part: _email.message.Message) -> str:
    raw = part.get_payload(decode=True) or b""
    if not isinstance(raw, bytes):
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _html_to_markdown(text: str) -> str:
    """Render an HTML email body to Markdown via :mod:`html2text`.

    Tuned for the agent's reading needs: links survive (``[text](url)``),
    paragraphs/lists/headings retain structure, ``<style>`` and ``<script>``
    contents are dropped, and HTML entities are unescaped.
    """
    return _html2md.handle(text).strip()
