"""``app.sock`` RPC handler: ``add`` / ``list`` / ``resolve`` / ``update`` / ``remove``.

The app server (UID ``computron``) is the only legitimate client. Per the
broker RPC framing, requests are length-prefixed JSON frames with
``{id, verb, args}`` and responses are ``{id, result | error}``. Verbs and
their payloads:

- ``add``: ``{slug, user_suffix, label, auth_blob, write_allowed}`` →
  ``{id, slug, label, write_allowed, capabilities, state, socket}``.
- ``list``: ``{}`` → ``{integrations: [...]}``. Non-secret metadata of
  every active integration.
- ``resolve``: ``{id}`` → ``{id, socket, write_allowed}``. The app server's
  broker_client calls this to locate a broker before any tool call.
- ``update``: ``{id, write_allowed}`` → the same record shape as ``add``.
  Rewrites meta, terminates the broker, re-spawns with new env so the
  broker's WRITE_ALLOWED gate reflects the new policy.
- ``remove``: ``{id}`` → ``{id}``. SIGTERMs broker, deletes vault files.

The handler is a thin dispatcher: it parses args and delegates to a
:class:`BrokerManager` (lifecycle) and :class:`Registry` (read access).

Errors use the shared ``RpcError`` machinery: the RPC layer turns them into
``{error: {code, message}}`` frames.
"""

from __future__ import annotations

import logging
from typing import Any

from integrations._rpc import RpcError
from integrations.supervisor._manager import BrokerManager
from integrations.supervisor._registry import Registry

logger = logging.getLogger(__name__)


class AppSockHandler:
    """Thin verb router — translates RPC frames into BrokerManager / Registry calls."""

    def __init__(
        self,
        *,
        manager: BrokerManager,
        registry: Registry,
    ) -> None:
        self._manager = manager
        self._registry = registry

    async def handle(self, verb: str, args: dict[str, Any]) -> dict[str, Any]:
        """Entry point called by the RPC layer for every incoming frame."""
        if verb == "add":
            return await self._add(args)
        if verb == "list":
            return self._list()
        if verb == "resolve":
            return self._resolve(args)
        if verb == "update":
            return await self._update(args)
        if verb == "remove":
            return await self._remove(args)
        msg = f"unknown verb: {verb}"
        raise RpcError("BAD_REQUEST", msg)

    # --- verbs --------------------------------------------------------------

    async def _add(self, args: dict[str, Any]) -> dict[str, Any]:
        record = await self._manager.add(
            slug=_require_str(args, "slug"),
            user_suffix=_require_str(args, "user_suffix"),
            label=_require_str(args, "label"),
            auth_blob=args.get("auth_blob"),
            write_allowed=bool(args.get("write_allowed", False)),
        )
        return _record_to_dict(record)

    def _list(self) -> dict[str, Any]:
        return {
            "integrations": [_record_to_dict(r) for r in self._registry.list()],
        }

    def _resolve(self, args: dict[str, Any]) -> dict[str, Any]:
        integration_id = _require_str(args, "id")
        record = self._registry.get(integration_id)
        if record is None:
            raise RpcError("NOT_FOUND", f"unknown integration: {integration_id}")
        return {
            "id": record.meta.id,
            "socket": str(record.broker.socket_path),
            "write_allowed": record.meta.write_allowed,
        }

    async def _update(self, args: dict[str, Any]) -> dict[str, Any]:
        integration_id = _require_str(args, "id")
        if "write_allowed" not in args:
            raise RpcError("BAD_REQUEST", "'write_allowed' required (bool)")
        write_allowed = bool(args["write_allowed"])
        record = await self._manager.update(
            integration_id, write_allowed=write_allowed,
        )
        return _record_to_dict(record)

    async def _remove(self, args: dict[str, Any]) -> dict[str, Any]:
        integration_id = _require_str(args, "id")
        await self._manager.remove(integration_id)
        return {"id": integration_id}


def _record_to_dict(record) -> dict[str, Any]:
    """Wire-shape for one integration — used by ``add`` and ``list``."""
    return {
        "id": record.meta.id,
        "slug": record.meta.slug,
        "label": record.meta.label,
        "write_allowed": record.meta.write_allowed,
        "capabilities": sorted(record.capabilities),
        "state": record.state,
        "socket": str(record.broker.socket_path),
    }


def _require_str(args: dict[str, Any], key: str) -> str:
    """Extract a required string arg or raise BAD_REQUEST."""
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise RpcError("BAD_REQUEST", f"{key!r} required (non-empty string)")
    return value
