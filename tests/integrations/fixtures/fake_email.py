"""In-process IMAP + SMTP fake for email-broker integration tests.

Two asyncio servers on port 0 (kernel-chosen), sharing one ``FakeEmail`` instance
that holds mailboxes and the outbox as plain dicts. Tests seed state before
pointing the broker at these servers and assert state after.

Supports the subset of IMAP / SMTP the email broker actually uses:

- IMAP (RFC 3501 subset): CAPABILITY, LOGIN, LOGOUT, LIST, SELECT, SEARCH ALL,
  UID FETCH, UID STORE (FLAGS), UID MOVE.
- SMTP (RFC 5321 subset): EHLO, AUTH PLAIN, MAIL FROM, RCPT TO, DATA, QUIT.

All plaintext — no TLS. Brokers under test connect with plain ``imaplib.IMAP4``
and plain ``smtplib.SMTP`` when ``IMAP_TLS=false`` / ``SMTP_STARTTLS=false``.

Configurable behaviors (each a simple attribute on the instance):

- ``reject_next_n_imap_logins``: count of LOGIN responses forced to NO-auth-failed.
  Decrements per attempt. The real broker exits 77 after 3 failures in 30 s.
- ``reject_next_n_smtp_auths``: same for SMTP AUTH.
- ``force_drop_next_imap``: next IMAP command causes the server to close the TCP
  connection without responding — exercises the broker's reconnect path.
"""

from __future__ import annotations

import asyncio
import base64
import email
import logging
import re
import uuid
from dataclasses import dataclass, field
from email.message import Message
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class _Message:
    """One in-memory email message in a mailbox."""

    uid: int
    raw: bytes                # full RFC 2822 bytes
    flags: set[str] = field(default_factory=set)

    @property
    def parsed(self) -> Message:
        return email.message_from_bytes(self.raw)

    def header_bytes(self) -> bytes:
        """Bytes from the start of ``raw`` up to and including the header/body separator."""
        sep = b"\r\n\r\n"
        idx = self.raw.find(sep)
        if idx == -1:
            # no body separator — treat entire bytes as headers
            return self.raw
        return self.raw[: idx + len(sep)]


@dataclass
class _Mailbox:
    """One IMAP mailbox (folder) with its messages and a UID counter."""

    name: str
    messages: list[_Message] = field(default_factory=list)
    next_uid: int = 1
    uid_validity: int = 1

    def append(self, raw: bytes, flags: set[str] | None = None) -> _Message:
        msg = _Message(uid=self.next_uid, raw=raw, flags=set(flags or ()))
        self.messages.append(msg)
        self.next_uid += 1
        return msg


@dataclass
class _Smtp:
    """One received SMTP message captured in the outbox."""

    mail_from: str
    rcpt_to: list[str]
    raw: bytes

    @property
    def parsed(self) -> Message:
        return email.message_from_bytes(self.raw)


class FakeEmail:
    """Holds IMAP mailboxes + the SMTP outbox. Run ``start()`` / ``stop()``."""

    def __init__(self, user: str = "larry@test.local", password: str = "app-pass-x") -> None:
        self.user = user
        self.password = password
        self.mailboxes: dict[str, _Mailbox] = {
            "INBOX": _Mailbox("INBOX"),
            "Sent": _Mailbox("Sent"),
            "Trash": _Mailbox("Trash"),
        }
        self.outbox: list[_Smtp] = []

        # Configurable failure modes (tests set these before running)
        self.reject_next_n_imap_logins: int = 0
        self.reject_next_n_smtp_auths: int = 0
        self.force_drop_next_imap: bool = False

        # Runtime server state
        self.imap_host: str = "127.0.0.1"
        self.imap_port: int = 0
        self.smtp_host: str = "127.0.0.1"
        self.smtp_port: int = 0
        self._imap_server: asyncio.base_events.Server | None = None
        self._smtp_server: asyncio.base_events.Server | None = None
        # Track every accepted connection's writer so stop() can force-close them.
        # asyncio.Server.wait_closed() blocks until all active connections finish,
        # so a test that exits without cleanly disconnecting its client would hang
        # the fixture teardown. We sidestep that by closing writers ourselves.
        self._active_writers: set[asyncio.StreamWriter] = set()

    # ----- seeding helpers -----

    def add_message(
        self,
        mailbox: str,
        *,
        from_: str,
        to: str,
        subject: str,
        body: str = "",
        attachments: list[tuple[str, str, bytes]] | None = None,
        flags: set[str] | None = None,
    ) -> int:
        """Build an RFC 2822 message and append it. Returns the UID.

        Without attachments this builds a flat ``text/plain`` message.
        With attachments it builds a ``multipart/mixed`` envelope where
        the first part is the body and each attachment is a separate
        part with ``Content-Disposition: attachment; filename=...``.
        ``attachments`` is a list of ``(filename, mime_type, payload)``
        tuples — the broker is expected to base64-decode the payload, so
        we base64-encode it here.
        """
        if attachments:
            raw = _build_multipart(
                from_=from_, to=to, subject=subject, body=body,
                attachments=attachments,
            )
        else:
            raw = (
                f"From: {from_}\r\n"
                f"To: {to}\r\n"
                f"Subject: {subject}\r\n"
                f"Message-ID: <{uuid.uuid4().hex}@test.local>\r\n"
                f"\r\n"
                f"{body}"
            ).encode("utf-8")
        mbox = self.mailboxes.setdefault(mailbox, _Mailbox(mailbox))
        return mbox.append(raw, flags).uid

    # ----- lifecycle -----

    async def start(self) -> None:
        self._imap_server = await asyncio.start_server(self._handle_imap, self.imap_host, 0)
        sockets = self._imap_server.sockets or ()
        if sockets:
            self.imap_port = sockets[0].getsockname()[1]

        self._smtp_server = await asyncio.start_server(self._handle_smtp, self.smtp_host, 0)
        sockets = self._smtp_server.sockets or ()
        if sockets:
            self.smtp_port = sockets[0].getsockname()[1]

    async def stop(self) -> None:
        # Force-close any writers we're still holding open. Without this
        # wait_closed() would block until every connected client disconnected
        # cleanly — and most tests won't bother to logout/quit before tearing
        # the fixture down.
        for writer in list(self._active_writers):
            try:
                writer.close()
            except Exception:  # noqa: BLE001
                pass
        self._active_writers.clear()
        for srv in (self._imap_server, self._smtp_server):
            if srv is not None:
                srv.close()
                await srv.wait_closed()
        self._imap_server = None
        self._smtp_server = None

    # =============================================================
    # IMAP subset (RFC 3501)
    # =============================================================

    async def _handle_imap(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._active_writers.add(writer)
        authenticated = False
        selected: _Mailbox | None = None
        try:
            writer.write(b"* OK [CAPABILITY IMAP4rev1 AUTH=PLAIN] FakeIMAP ready\r\n")
            await writer.drain()

            while True:
                line = await reader.readline()
                if not line:
                    return
                if self.force_drop_next_imap:
                    self.force_drop_next_imap = False
                    logger.info("fake_email: forcing IMAP TCP drop")
                    writer.close()
                    return
                tag, cmd_line = _parse_imap_line(line)
                if not cmd_line:
                    writer.write(f"{tag} BAD empty command\r\n".encode())
                    await writer.drain()
                    continue

                cmd, _, rest = cmd_line.partition(" ")
                cmd_upper = cmd.upper()

                if cmd_upper == "CAPABILITY":
                    writer.write(b"* CAPABILITY IMAP4rev1 AUTH=PLAIN\r\n")
                    writer.write(f"{tag} OK CAPABILITY completed\r\n".encode())

                elif cmd_upper == "LOGIN":
                    if self.reject_next_n_imap_logins > 0:
                        self.reject_next_n_imap_logins -= 1
                        writer.write(f"{tag} NO LOGIN rejected\r\n".encode())
                    else:
                        parts = _split_imap_args(rest)
                        user = parts[0].strip('"') if parts else ""
                        pw = parts[1].strip('"') if len(parts) > 1 else ""
                        if user == self.user and pw == self.password:
                            authenticated = True
                            writer.write(f"{tag} OK LOGIN completed\r\n".encode())
                        else:
                            writer.write(f"{tag} NO LOGIN rejected\r\n".encode())

                elif cmd_upper == "LOGOUT":
                    writer.write(b"* BYE bye\r\n")
                    writer.write(f"{tag} OK LOGOUT completed\r\n".encode())
                    await writer.drain()
                    return

                elif not authenticated:
                    writer.write(f"{tag} NO Must LOGIN first\r\n".encode())

                elif cmd_upper == "LIST":
                    # LIST "" "*"  (or variations). Reply with every mailbox.
                    for name in self.mailboxes:
                        writer.write(f'* LIST (\\HasNoChildren) "/" "{name}"\r\n'.encode())
                    writer.write(f"{tag} OK LIST completed\r\n".encode())

                elif cmd_upper == "SELECT":
                    try:
                        name, leftover = _parse_imap_arg(rest)
                    except _ImapParseError as exc:
                        writer.write(f"{tag} BAD {exc}\r\n".encode())
                        await writer.drain()
                        continue
                    if leftover:
                        # Same shape real iCloud/Gmail return when an
                        # unquoted folder name with a space is sent: an
                        # extra token shows up after the mailbox arg.
                        writer.write(f"{tag} BAD Could not parse command\r\n".encode())
                        await writer.drain()
                        continue
                    mbox = self.mailboxes.get(name)
                    if mbox is None:
                        writer.write(f"{tag} NO No such mailbox\r\n".encode())
                    else:
                        selected = mbox
                        writer.write(f"* {len(mbox.messages)} EXISTS\r\n".encode())
                        writer.write(b"* 0 RECENT\r\n")
                        writer.write(f"* OK [UIDVALIDITY {mbox.uid_validity}] ok\r\n".encode())
                        writer.write(f"* OK [UIDNEXT {mbox.next_uid}] ok\r\n".encode())
                        writer.write(f"{tag} OK [READ-WRITE] SELECT completed\r\n".encode())

                elif cmd_upper == "SEARCH":
                    # Plain SEARCH — returns sequence numbers (1..N positions).
                    # Honors ``ALL`` and ``TEXT "query"``; the latter does a
                    # naive substring match against each message's full bytes,
                    # which is enough to exercise the broker's match/no-match
                    # paths against the fake.
                    if selected is None:
                        writer.write(f"{tag} BAD Must SELECT first\r\n".encode())
                    else:
                        seqs = _eval_search_criteria(rest, selected.messages)
                        if seqs is None:
                            writer.write(f"{tag} BAD Could not parse SEARCH\r\n".encode())
                        else:
                            line = " ".join(str(s) for s in seqs)
                            writer.write(f"* SEARCH {line}\r\n".encode())
                            writer.write(f"{tag} OK SEARCH completed\r\n".encode())

                elif cmd_upper == "FETCH":
                    # Plain FETCH — same shape as UID FETCH but the id-set is
                    # sequence numbers, not UIDs. Translates each seq to its
                    # message by 1-based position in the mailbox list.
                    if selected is None:
                        writer.write(f"{tag} BAD Must SELECT first\r\n".encode())
                        continue
                    seq_set, _, items = rest.partition(" ")
                    items = items.strip()
                    target_msgs: list[_Message] = []
                    for piece in seq_set.strip().split(","):
                        piece = piece.strip()
                        if not piece:
                            continue
                        try:
                            n = int(piece)
                        except ValueError:
                            continue
                        if 1 <= n <= len(selected.messages):
                            target_msgs.append(selected.messages[n - 1])
                    items_upper = items.upper()
                    header_fields = _parse_header_fields(items_upper)
                    want_body = (
                        "BODY[]" in items_upper
                        or "BODY.PEEK[]" in items_upper
                        or "RFC822" in items_upper
                    )
                    want_header = (
                        "BODY.PEEK[HEADER]" in items_upper
                        or "BODY[HEADER]" in items_upper
                    )
                    for msg in target_msgs:
                        parts: list[str] = [f"UID {msg.uid}"]
                        payload_bytes = b""
                        if want_body:
                            payload_bytes = msg.raw
                            parts.append(f"BODY[] {{{len(payload_bytes)}}}")
                        elif header_fields is not None:
                            payload_bytes = _extract_header_fields(msg.raw, header_fields)
                            field_list = " ".join(header_fields)
                            parts.append(
                                f"BODY[HEADER.FIELDS ({field_list})] {{{len(payload_bytes)}}}",
                            )
                        elif want_header:
                            payload_bytes = msg.header_bytes()
                            parts.append(f"BODY[HEADER] {{{len(payload_bytes)}}}")
                        seq = selected.messages.index(msg) + 1
                        writer.write(f"* {seq} FETCH ({' '.join(parts)}".encode())
                        if payload_bytes:
                            writer.write(b"\r\n")
                            writer.write(payload_bytes)
                            writer.write(b")\r\n")
                        else:
                            writer.write(b")\r\n")
                    writer.write(f"{tag} OK FETCH completed\r\n".encode())

                elif cmd_upper == "UID" and rest.upper().startswith("SEARCH"):
                    # UID SEARCH ALL — return all UIDs in the selected mailbox.
                    # (We don't implement criteria parsing for v1; "ALL" is enough for happy tests.)
                    if selected is None:
                        writer.write(f"{tag} BAD Must SELECT first\r\n".encode())
                    else:
                        uids = " ".join(str(m.uid) for m in selected.messages)
                        writer.write(f"* SEARCH {uids}\r\n".encode())
                        writer.write(f"{tag} OK SEARCH completed\r\n".encode())

                elif cmd_upper == "UID" and rest.upper().startswith("FETCH"):
                    # UID FETCH <uid-set> (<items>)
                    if selected is None:
                        writer.write(f"{tag} BAD Must SELECT first\r\n".encode())
                        continue
                    _, _, fetch_args = rest.partition(" ")
                    uid_set, _, items = fetch_args.partition(" ")
                    items = items.strip()
                    target_uids = _parse_uid_set(uid_set.strip(), selected)
                    items_upper = items.upper()
                    want_header = "BODY.PEEK[HEADER]" in items_upper or "BODY[HEADER]" in items_upper
                    want_body = (
                        "BODY[]" in items_upper
                        or "BODY.PEEK[]" in items_upper
                        or "RFC822" in items_upper
                    )
                    want_flags = "FLAGS" in items_upper
                    # Partial-header request: ``BODY.PEEK[HEADER.FIELDS (FROM TO ..)]``.
                    # Real servers return only the named header lines; we
                    # extract them out of the message's full header block so
                    # the wire shape matches.
                    header_fields = _parse_header_fields(items_upper)
                    for uid in target_uids:
                        msg = next((m for m in selected.messages if m.uid == uid), None)
                        if msg is None:
                            continue
                        parts: list[str] = [f"UID {uid}"]
                        if want_flags:
                            parts.append("FLAGS (" + " ".join(sorted(msg.flags)) + ")")
                        payload_bytes = b""
                        if want_body:
                            payload_bytes = msg.raw
                            parts.append(f"BODY[] {{{len(payload_bytes)}}}")
                        elif header_fields is not None:
                            payload_bytes = _extract_header_fields(msg.raw, header_fields)
                            field_list = " ".join(header_fields)
                            parts.append(
                                f"BODY[HEADER.FIELDS ({field_list})] {{{len(payload_bytes)}}}",
                            )
                        elif want_header:
                            payload_bytes = msg.header_bytes()
                            parts.append(f"BODY[HEADER] {{{len(payload_bytes)}}}")
                        seq = selected.messages.index(msg) + 1
                        writer.write(f"* {seq} FETCH ({' '.join(parts)}".encode())
                        if payload_bytes:
                            writer.write(b"\r\n")
                            writer.write(payload_bytes)
                            writer.write(b")\r\n")
                        else:
                            writer.write(b")\r\n")
                    writer.write(f"{tag} OK FETCH completed\r\n".encode())

                elif cmd_upper == "UID" and rest.upper().startswith("STORE"):
                    # UID STORE <uid-set> +FLAGS (\Seen)  — or -FLAGS, or FLAGS
                    if selected is None:
                        writer.write(f"{tag} BAD Must SELECT first\r\n".encode())
                        continue
                    _, _, store_args = rest.partition(" ")
                    uid_set, _, store_rest = store_args.partition(" ")
                    op, _, flaglist = store_rest.partition(" ")
                    flags_to_change = _parse_flag_list(flaglist)
                    target_uids = _parse_uid_set(uid_set.strip(), selected)
                    for uid in target_uids:
                        msg = next((m for m in selected.messages if m.uid == uid), None)
                        if msg is None:
                            continue
                        if op.upper() == "+FLAGS" or op.upper() == "+FLAGS.SILENT":
                            msg.flags |= flags_to_change
                        elif op.upper() == "-FLAGS" or op.upper() == "-FLAGS.SILENT":
                            msg.flags -= flags_to_change
                        else:
                            msg.flags = set(flags_to_change)
                        if not op.upper().endswith(".SILENT"):
                            seq = selected.messages.index(msg) + 1
                            flags_str = " ".join(sorted(msg.flags))
                            writer.write(
                                f"* {seq} FETCH (UID {uid} FLAGS ({flags_str}))\r\n".encode()
                            )
                    writer.write(f"{tag} OK STORE completed\r\n".encode())

                elif cmd_upper == "UID" and rest.upper().startswith("MOVE"):
                    if selected is None:
                        writer.write(f"{tag} BAD Must SELECT first\r\n".encode())
                        continue
                    _, _, move_args = rest.partition(" ")
                    uid_set, _, dest_rest = move_args.partition(" ")
                    try:
                        dest, leftover = _parse_imap_arg(dest_rest)
                    except _ImapParseError as exc:
                        writer.write(f"{tag} BAD {exc}\r\n".encode())
                        await writer.drain()
                        continue
                    if leftover:
                        writer.write(f"{tag} BAD Could not parse command\r\n".encode())
                        await writer.drain()
                        continue
                    target_uids = _parse_uid_set(uid_set.strip(), selected)
                    dest_mbox = self.mailboxes.setdefault(dest, _Mailbox(dest))
                    for uid in target_uids:
                        msg = next((m for m in selected.messages if m.uid == uid), None)
                        if msg is None:
                            continue
                        selected.messages.remove(msg)
                        new_msg = dest_mbox.append(msg.raw, msg.flags)
                        writer.write(f"* OK [COPYUID 1 {uid} {new_msg.uid}] moved\r\n".encode())
                    writer.write(f"{tag} OK MOVE completed\r\n".encode())

                elif cmd_upper == "NOOP":
                    writer.write(f"{tag} OK NOOP completed\r\n".encode())

                else:
                    writer.write(f"{tag} BAD unknown command: {cmd}\r\n".encode())

                await writer.drain()
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                logger.debug("IMAP connection close suppressed", exc_info=True)
            self._active_writers.discard(writer)

    # =============================================================
    # SMTP subset (RFC 5321)
    # =============================================================

    async def _handle_smtp(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._active_writers.add(writer)
        state: dict[str, Any] = {
            "authenticated": False,
            "mail_from": None,
            "rcpt_to": [],
        }
        try:
            writer.write(b"220 fake.local ESMTP ready\r\n")
            await writer.drain()

            while True:
                line = await reader.readline()
                if not line:
                    return
                cmd_line = line.decode("utf-8", errors="replace").rstrip("\r\n")
                upper = cmd_line.upper()

                if upper.startswith("EHLO") or upper.startswith("HELO"):
                    writer.write(b"250-fake.local\r\n")
                    writer.write(b"250-AUTH PLAIN LOGIN\r\n")
                    writer.write(b"250 HELP\r\n")

                elif upper.startswith("AUTH PLAIN"):
                    # AUTH PLAIN <b64 \0user\0pass>
                    _, _, payload = cmd_line.partition(" ")
                    _, _, b64 = payload.partition(" ")
                    if self.reject_next_n_smtp_auths > 0:
                        self.reject_next_n_smtp_auths -= 1
                        writer.write(b"535 5.7.8 Authentication failed\r\n")
                    elif _verify_auth_plain(b64, self.user, self.password):
                        state["authenticated"] = True
                        writer.write(b"235 2.7.0 Authentication successful\r\n")
                    else:
                        writer.write(b"535 5.7.8 Authentication failed\r\n")

                elif upper.startswith("MAIL FROM:"):
                    if not state["authenticated"]:
                        writer.write(b"530 5.7.0 Authentication required\r\n")
                    else:
                        state["mail_from"] = _extract_email(cmd_line.split(":", 1)[1])
                        state["rcpt_to"] = []
                        writer.write(b"250 2.1.0 OK\r\n")

                elif upper.startswith("RCPT TO:"):
                    if not state["mail_from"]:
                        writer.write(b"503 5.5.1 MAIL first\r\n")
                    else:
                        state["rcpt_to"].append(_extract_email(cmd_line.split(":", 1)[1]))
                        writer.write(b"250 2.1.5 OK\r\n")

                elif upper == "DATA":
                    if not state["rcpt_to"]:
                        writer.write(b"503 5.5.1 RCPT first\r\n")
                        await writer.drain()
                        continue
                    writer.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                    await writer.drain()
                    body = bytearray()
                    while True:
                        chunk = await reader.readline()
                        if not chunk:
                            return
                        if chunk == b".\r\n":
                            break
                        # dot-unstuff: lines starting ".." become "."
                        if chunk.startswith(b".."):
                            chunk = chunk[1:]
                        body.extend(chunk)
                    mail_from_value = state["mail_from"] or ""
                    self.outbox.append(
                        _Smtp(
                            mail_from=mail_from_value,
                            rcpt_to=list(state["rcpt_to"]),
                            raw=bytes(body),
                        )
                    )
                    state["mail_from"] = None
                    state["rcpt_to"] = []
                    writer.write(b"250 2.0.0 Message accepted\r\n")

                elif upper == "QUIT":
                    writer.write(b"221 2.0.0 bye\r\n")
                    await writer.drain()
                    return

                elif upper == "RSET":
                    state["mail_from"] = None
                    state["rcpt_to"] = []
                    writer.write(b"250 2.0.0 OK\r\n")

                elif upper == "NOOP":
                    writer.write(b"250 2.0.0 OK\r\n")

                else:
                    writer.write(b"502 5.5.1 Command not implemented\r\n")

                await writer.drain()
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                logger.debug("SMTP connection close suppressed", exc_info=True)
            self._active_writers.discard(writer)


# =============================================================
# helpers
# =============================================================


def _parse_imap_line(line: bytes) -> tuple[str, str]:
    """Return ``(tag, rest)`` from an IMAP command line. Trailing CRLF stripped."""
    text = line.decode("utf-8", errors="replace").rstrip("\r\n")
    tag, _, rest = text.partition(" ")
    return tag, rest


def _build_multipart(
    *,
    from_: str,
    to: str,
    subject: str,
    body: str,
    attachments: list[tuple[str, str, bytes]],
) -> bytes:
    """Construct a ``multipart/mixed`` RFC 2822 byte blob.

    Used by :meth:`FakeEmail.add_message` when attachments are present.
    Each attachment becomes a leaf part with ``Content-Disposition:
    attachment; filename="..."`` and base64-encoded body, which is the
    shape Python's ``email`` parser expects to decode back to bytes.
    """
    boundary = f"=={uuid.uuid4().hex[:24]}=="
    lines: list[str] = [
        f"From: {from_}",
        f"To: {to}",
        f"Subject: {subject}",
        f"Message-ID: <{uuid.uuid4().hex}@test.local>",
        "MIME-Version: 1.0",
        f'Content-Type: multipart/mixed; boundary="{boundary}"',
        "",
        "This is a multipart message in MIME format.",
        f"--{boundary}",
        'Content-Type: text/plain; charset="utf-8"',
        "Content-Transfer-Encoding: 7bit",
        "",
        body,
    ]
    for filename, mime_type, payload in attachments:
        encoded = base64.b64encode(payload).decode("ascii")
        # Wrap base64 to 76-char lines per RFC 2045.
        wrapped = "\r\n".join(
            encoded[i:i + 76] for i in range(0, len(encoded), 76)
        )
        lines.extend([
            f"--{boundary}",
            f"Content-Type: {mime_type}",
            "Content-Transfer-Encoding: base64",
            f'Content-Disposition: attachment; filename="{filename}"',
            "",
            wrapped,
        ])
    lines.append(f"--{boundary}--")
    return "\r\n".join(lines).encode("utf-8")


_HEADER_FIELDS_RE = re.compile(r"BODY(?:\.PEEK)?\[HEADER\.FIELDS \(([^)]+)\)\]")


def _eval_search_criteria(rest: str, messages: list[_Message]) -> list[int] | None:
    """Evaluate a plain ``SEARCH`` criteria string; return sequence numbers.

    Supports ``ALL`` (every message) and ``TEXT "query"`` (substring match
    against the full raw bytes of each message). Anything else returns
    ``None`` so the handler can respond ``BAD``. Sequence numbers are
    1-based positions in ``messages``.
    """
    rest = rest.strip()
    if rest.upper() == "ALL":
        return list(range(1, len(messages) + 1))
    if rest.upper().startswith("TEXT "):
        try:
            query, leftover = _parse_imap_arg(rest[5:])
        except _ImapParseError:
            return None
        if leftover:
            return None
        needle = query.encode("utf-8", errors="replace").lower()
        return [
            i + 1 for i, m in enumerate(messages)
            if needle in m.raw.lower()
        ]
    return None


def _parse_header_fields(items_upper: str) -> list[str] | None:
    """Extract the field list from ``BODY[.PEEK][HEADER.FIELDS (A B C)]``.

    Returns ``None`` if the items spec doesn't include a HEADER.FIELDS
    clause. Returns the field names (uppercased) otherwise.
    """
    match = _HEADER_FIELDS_RE.search(items_upper)
    if not match:
        return None
    return match.group(1).split()


def _extract_header_fields(raw: bytes, fields: list[str]) -> bytes:
    """Return only the named header lines from a full RFC 822 message blob.

    Mirrors what real IMAP servers do for ``BODY[HEADER.FIELDS (...)]``:
    only the listed headers (case-insensitive) plus a trailing CRLF.
    """
    sep = b"\r\n\r\n"
    end = raw.find(sep)
    header_block = raw[:end] if end != -1 else raw
    wanted = {f.upper() for f in fields}
    out: list[bytes] = []
    for line in header_block.split(b"\r\n"):
        if not line:
            continue
        name, _, _ = line.partition(b":")
        if name.strip().upper().decode("ascii", errors="replace") in wanted:
            out.append(line)
    if out:
        return b"\r\n".join(out) + b"\r\n\r\n"
    return b"\r\n"


class _ImapParseError(Exception):
    """Raised when an IMAP arg can't be parsed; the handler turns this into a BAD reply."""


def _parse_imap_arg(rest: str) -> tuple[str, str]:
    r"""Parse one IMAP arg (quoted string or atom) from ``rest``.

    Returns ``(value, leftover)``. The leftover is the remaining text
    after the arg with any leading whitespace stripped. A quoted form
    like ``"Sent Messages" something`` returns ``("Sent Messages", "something")``;
    an unquoted form like ``Sent Messages`` returns ``("Sent", "Messages")``
    so the caller can detect the trailing-token-was-not-empty case and
    respond ``BAD`` (mirrors what real iCloud/Gmail do for unquoted
    multi-token folder names).

    Raises :class:`_ImapParseError` on a quoted string that never closes.
    """
    rest = rest.lstrip()
    if not rest:
        raise _ImapParseError("missing argument")
    if rest.startswith('"'):
        out: list[str] = []
        i = 1
        while i < len(rest):
            c = rest[i]
            if c == "\\" and i + 1 < len(rest):
                out.append(rest[i + 1])
                i += 2
                continue
            if c == '"':
                return "".join(out), rest[i + 1:].lstrip()
            out.append(c)
            i += 1
        raise _ImapParseError("unterminated quoted string")
    head, _, tail = rest.partition(" ")
    return head, tail.lstrip()


def _split_imap_args(text: str) -> list[str]:
    """Crude quoted-string-aware argument split. Fine for our subset."""
    parts: list[str] = []
    buf: list[str] = []
    in_quotes = False
    for ch in text:
        if ch == '"':
            in_quotes = not in_quotes
            buf.append(ch)
        elif ch == " " and not in_quotes:
            if buf:
                parts.append("".join(buf))
                buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


def _parse_uid_set(uid_set: str, mbox: _Mailbox) -> list[int]:
    """Parse ``1:5,7,9:*`` into a concrete uid list against the mailbox."""
    uids: list[int] = []
    existing = {m.uid for m in mbox.messages}
    max_uid = max(existing) if existing else 0
    for piece in uid_set.split(","):
        piece = piece.strip()
        if ":" in piece:
            lo, _, hi = piece.partition(":")
            lo_i = int(lo) if lo != "*" else max_uid
            hi_i = int(hi) if hi != "*" else max_uid
            if lo_i > hi_i:
                lo_i, hi_i = hi_i, lo_i
            uids.extend(u for u in range(lo_i, hi_i + 1) if u in existing)
        else:
            try:
                u = int(piece)
            except ValueError:
                continue
            if u in existing:
                uids.append(u)
    return uids


def _parse_flag_list(text: str) -> set[str]:
    """Parse ``(\\Seen \\Answered)`` into ``{"\\\\Seen", "\\\\Answered"}``."""
    text = text.strip()
    if text.startswith("("):
        text = text[1:]
    if text.endswith(")"):
        text = text[:-1]
    return {tok for tok in text.split() if tok}


def _verify_auth_plain(b64: str, user: str, password: str) -> bool:
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return False
    # AUTH PLAIN layout: \0username\0password
    parts = raw.split(b"\x00")
    if len(parts) != 3:
        return False
    return parts[1].decode("utf-8", errors="replace") == user and parts[
        2
    ].decode("utf-8", errors="replace") == password


def _extract_email(text: str) -> str:
    """Pull the address out of ``<addr@host>`` or return the stripped arg."""
    text = text.strip()
    if text.startswith("<") and ">" in text:
        return text[1 : text.index(">")]
    return text.split()[0] if text else ""
