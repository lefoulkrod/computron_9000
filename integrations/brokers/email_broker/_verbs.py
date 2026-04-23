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
from integrations.brokers.email_broker._imap_client import ImapClient

# Authoritative read/write classification for email-broker verbs.
# Must stay in lockstep with ``broker_client._verb_types._VERB_TYPES`` on the
# app-server side — a drift-check unit test will eventually assert they agree.
# Until that test lands, keep this the single on-broker source of truth.
_VERB_TYPE: dict[str, Literal["read", "write"]] = {
    "list_mailboxes": "read",
    "search_messages": "read",
    "fetch_message": "read",
    "fetch_headers": "read",
    "fetch_attachment": "read",
    "flag_message": "write",
    "move_message": "write",
    "send_message": "write",
}


_Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class VerbDispatcher:
    """Route one RPC verb call to the right client method."""

    def __init__(
        self,
        imap: ImapClient,
        # smtp will be wired in a follow-up; walking skeleton only covers read verbs.
        smtp: Any | None,
        *,
        write_allowed: bool,
    ) -> None:
        self._imap = imap
        self._smtp = smtp
        self._write_allowed = write_allowed

        # Handler registry — grows as verbs land. Everything in ``_VERB_TYPE``
        # that lacks a handler here falls through to "not implemented."
        self._handlers: dict[str, _Handler] = {
            "list_mailboxes": self._handle_list_mailboxes,
        }

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
