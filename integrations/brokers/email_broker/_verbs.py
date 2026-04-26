"""Verb dispatcher for the email broker.

Bridges two layers with different vocabularies:

- The RPC layer (``integrations._rpc``) speaks frames: ``(verb_name, args_dict)
  -> result_dict``. It has no idea what verbs exist or what they do.
- The client layer (``_imap_client``, ``_smtp_client``) speaks email: typed
  method calls, typed returns.

The dispatcher:

1. Looks up each verb's ``"read"`` / ``"write"`` tag.
2. Refuses write verbs when ``WRITE_ALLOWED=false``. This is the load-bearing
   permission gate — an agent bypassing the app server by connecting straight
   to the broker's UDS still hits this check.
3. Finds the handler for the verb and calls it with the args dict; the handler
   in turn calls the client's typed method and packages the result.

Verbs present in ``_VERB_TYPE`` but absent from ``_handlers`` are "declared but
not implemented" — they return ``BAD_REQUEST`` until we wire them up. That lets
the walking-skeleton broker declare its intended surface area while only a
subset works.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from integrations._rpc import RpcError
from integrations.brokers.email_broker._caldav_client import CalDavClient
from integrations.brokers.email_broker._imap_client import ImapClient
from integrations.brokers.email_broker._smtp_client import SmtpClient

# Authoritative read/write classification for email-broker verbs. The
# app-server side keeps a parallel table at ``broker_client._verb_types``;
# ``tests/integrations/test_verb_types_drift.py`` asserts the two agree.
_VERB_TYPE: dict[str, Literal["read", "write"]] = {
    # Email
    "list_mailboxes": "read",
    "list_messages": "read",
    "search_messages": "read",
    "fetch_message": "read",
    "fetch_attachment": "read",
    "move_message": "write",
    "send_message": "write",
    # Calendar (CalDAV)
    "list_calendars": "read",
    "list_events": "read",
    "create_event": "write",
    "delete_event": "write",
}


_Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class VerbDispatcher:
    """Route one RPC verb call to the right client method."""

    def __init__(
        self,
        imap: ImapClient,
        # SMTP is None when the catalog entry doesn't set SMTP_HOST (no
        # outbound path configured); send_message then returns "not
        # implemented" so the gate decision and the missing-config decision
        # are visibly distinct.
        smtp: SmtpClient | None,
        # caldav is None for catalog entries that don't declare the
        # calendar capability; calendar verbs return "not implemented" then.
        caldav: CalDavClient | None = None,
        *,
        write_allowed: bool,
    ) -> None:
        self._imap = imap
        self._smtp = smtp
        self._caldav = caldav
        self._write_allowed = write_allowed

        # Handler registry — grows as verbs land. Everything in ``_VERB_TYPE``
        # that lacks a handler here falls through to "not implemented."
        self._handlers: dict[str, _Handler] = {
            "list_mailboxes": self._handle_list_mailboxes,
            "list_messages": self._handle_list_messages,
            "search_messages": self._handle_search_messages,
            "fetch_message": self._handle_fetch_message,
            "move_message": self._handle_move_message,
        }
        if smtp is not None:
            self._handlers["send_message"] = self._handle_send_message
        if caldav is not None:
            self._handlers["list_calendars"] = self._handle_list_calendars
            self._handlers["list_events"] = self._handle_list_events

    async def dispatch(self, verb: str, args: dict[str, Any]) -> dict[str, Any]:
        """Entry point called by the RPC layer for every incoming frame."""
        verb_type = _VERB_TYPE.get(verb)
        if verb_type is None:
            # Not on the declared surface at all. Distinguishes "typo" from
            # "declared but not yet implemented" below.
            msg = f"unknown verb: {verb}"
            raise RpcError("BAD_REQUEST", msg)

        # WRITE_ALLOWED gate. Checked before handler lookup on purpose:
        #  - Every declared write verb returns ``WRITE_DENIED`` consistently,
        #    whether or not it has a handler wired yet. Without this ordering,
        #    a write verb without a handler would return "not implemented" while
        #    the same verb with a handler would return "WRITE_DENIED" — two
        #    different responses for what should be one policy decision.
        #  - New write verbs added to ``_VERB_TYPE`` fail the gate before anyone
        #    looks up their handler, so we can't accidentally expose a new write
        #    path by adding an entry to ``_VERB_TYPE`` before wiring the handler.
        # (Not for information hiding — unknown verbs already return a specific
        # error above, so the verb surface is enumerable regardless.)
        if verb_type == "write" and not self._write_allowed:
            msg = "writes disabled for this integration"
            raise RpcError("WRITE_DENIED", msg)

        handler = self._handlers.get(verb)
        if handler is None:
            # Declared in _VERB_TYPE but no handler wired yet — walking skeleton
            # or a verb on the roadmap.
            msg = f"verb not implemented: {verb}"
            raise RpcError("BAD_REQUEST", msg)

        return await handler(args)

    # --- handlers -----------------------------------------------------------

    async def _handle_list_mailboxes(self, _args: dict[str, Any]) -> dict[str, Any]:
        """``list_mailboxes`` takes no args; returns ``{"mailboxes": [...]}``.

        The client returns typed :class:`Mailbox` instances; we serialize via
        ``.model_dump()`` here because this is the wire boundary — the dict
        returned from this handler goes straight into the JSON RPC frame.
        """
        mailboxes = await self._imap.list_mailboxes()
        return {"mailboxes": [m.model_dump() for m in mailboxes]}

    async def _handle_list_messages(self, args: dict[str, Any]) -> dict[str, Any]:
        """``list_messages {folder, limit}`` → ``{headers: [...]}``."""
        folder = _require_str(args, "folder")
        limit = _require_int(args, "limit", default=20)
        headers = await self._imap.list_messages(folder, limit)
        return {"headers": [h.model_dump() for h in headers]}

    async def _handle_search_messages(self, args: dict[str, Any]) -> dict[str, Any]:
        """``search_messages {folder, query, limit}`` → ``{headers: [...]}``."""
        folder = _require_str(args, "folder")
        query = _require_str(args, "query")
        limit = _require_int(args, "limit", default=20)
        headers = await self._imap.search_messages(folder, query, limit)
        return {"headers": [h.model_dump() for h in headers]}

    async def _handle_fetch_message(self, args: dict[str, Any]) -> dict[str, Any]:
        """``fetch_message {folder, uid}`` → ``{message: {header, body_text}}``."""
        folder = _require_str(args, "folder")
        uid = _require_str(args, "uid")
        try:
            message = await self._imap.fetch_message(folder, uid)
        except LookupError as exc:
            raise RpcError("NOT_FOUND", str(exc)) from exc
        return {"message": message.model_dump()}

    async def _handle_move_message(self, args: dict[str, Any]) -> dict[str, Any]:
        """``move_message {folder, uid, dest_folder}`` → ``{moved: true}``.

        The verb returns a thin acknowledgment because UID MOVE assigns a
        new UID at the destination that the caller didn't ask for; if a
        future verb needs the new UID we can extend the response then.
        """
        folder = _require_str(args, "folder")
        uid = _require_str(args, "uid")
        dest_folder = _require_str(args, "dest_folder")
        try:
            await self._imap.move_message(folder, uid, dest_folder)
        except LookupError as exc:
            raise RpcError("NOT_FOUND", str(exc)) from exc
        return {"moved": True}

    async def _handle_send_message(self, args: dict[str, Any]) -> dict[str, Any]:
        """``send_message {to, subject, body}`` → ``{sent: true, message_id}``.

        ``to`` is a JSON array of bare addresses. The broker does not validate
        addresses; the upstream MTA does, and we surface its rejection
        unchanged.
        """
        if self._smtp is None:
            raise RpcError("BAD_REQUEST", "smtp not configured for this integration")
        to = _require_str_list(args, "to")
        subject = _require_str(args, "subject")
        body = _require_str(args, "body")
        message_id = await self._smtp.send_message(
            to=to, subject=subject, body=body,
        )
        return {"sent": True, "message_id": message_id}

    async def _handle_list_calendars(self, _args: dict[str, Any]) -> dict[str, Any]:
        """``list_calendars`` takes no args; returns ``{"calendars": [...]}``."""
        if self._caldav is None:
            raise RpcError("BAD_REQUEST", "calendar not configured for this integration")
        calendars = await self._caldav.list_calendars()
        return {"calendars": [c.model_dump() for c in calendars]}

    async def _handle_list_events(self, args: dict[str, Any]) -> dict[str, Any]:
        """``list_events {calendar_url, days_forward, days_back, limit}`` → ``{calendar_name, events: [...]}``."""
        if self._caldav is None:
            raise RpcError("BAD_REQUEST", "calendar not configured for this integration")
        calendar_url = _require_str(args, "calendar_url")
        days_forward = _require_int(args, "days_forward", default=30)
        days_back = _require_int(args, "days_back", default=0)
        limit = _require_int(args, "limit", default=50)
        name, events = await self._caldav.list_events(
            calendar_url, days_forward, days_back, limit,
        )
        return {
            "calendar_name": name,
            "events": [e.model_dump() for e in events],
        }


def _require_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise RpcError("BAD_REQUEST", f"{key!r} required (non-empty string)")
    return value


def _require_int(args: dict[str, Any], key: str, *, default: int) -> int:
    value = args.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RpcError("BAD_REQUEST", f"{key!r} must be an integer")
    return value


def _require_str_list(args: dict[str, Any], key: str) -> list[str]:
    """Require ``key`` to be a non-empty JSON array of non-empty strings."""
    value = args.get(key)
    if not isinstance(value, list) or not value:
        raise RpcError("BAD_REQUEST", f"{key!r} required (non-empty array of strings)")
    if not all(isinstance(v, str) and v for v in value):
        raise RpcError("BAD_REQUEST", f"{key!r} must contain non-empty strings")
    return list(value)
