"""Verb dispatcher for the Google Workspace broker.

Phase 1 ships an empty dispatcher — no API verbs are wired yet, but the
broker still serves its UDS so the supervisor can lifecycle-manage it
and the agent's tool registry sees the integration as ``running``.
Phase 2 fills in the read verbs (Gmail / Calendar / Drive / Contacts);
Phase 4 adds writes.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from google.auth.transport.requests import AuthorizedSession

from integrations._rpc import RpcError

logger = logging.getLogger(__name__)


# Authoritative read/write classification mirrored on the app-server side
# in ``broker_client._verb_types``. The drift-check test asserts the two
# tables agree. Empty in Phase 1 — verbs land in Phases 2-4.
_VERB_TYPE: dict[str, Literal["read", "write"]] = {}


_Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class VerbDispatcher:
    """Route one RPC verb call to the right Google API client method."""

    def __init__(
        self,
        session: AuthorizedSession,
        *,
        write_allowed: bool,
    ) -> None:
        self._session = session
        self._write_allowed = write_allowed

        # Handler registry — grows as verbs land in Phases 2-4. Same shape
        # as the email broker's dispatcher.
        self._handlers: dict[str, _Handler] = {}

    async def dispatch(self, verb: str, args: dict[str, Any]) -> dict[str, Any]:
        """Entry point called by the RPC layer for every incoming frame."""
        verb_type = _VERB_TYPE.get(verb)
        if verb_type is None:
            msg = f"unknown verb: {verb}"
            raise RpcError("BAD_REQUEST", msg)

        # WRITE_ALLOWED gate. Checked before handler lookup so every
        # declared write verb returns ``WRITE_DENIED`` consistently —
        # whether or not it has a handler wired yet — and so a new write
        # verb added to ``_VERB_TYPE`` fails the gate before anyone looks
        # up its handler.
        if verb_type == "write" and not self._write_allowed:
            raise RpcError(
                "WRITE_DENIED",
                f"writes are disabled for this integration; "
                f"verb {verb!r} requires write_allowed=true",
            )

        handler = self._handlers.get(verb)
        if handler is None:
            msg = f"verb not implemented: {verb}"
            raise RpcError("BAD_REQUEST", msg)
        return await handler(args)
