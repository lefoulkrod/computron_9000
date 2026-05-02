"""``app.sock`` RPC handler: ``add`` / ``list`` / ``resolve`` / ``update`` / ``remove``.

The app server (UID ``computron``) is the only legitimate client. Per the
broker RPC framing, requests are length-prefixed JSON frames with
``{id, verb, args}`` and responses are ``{id, result | error}``. Verbs and
their payloads:

- ``add``: ``{slug, user_suffix, label, auth_blob, write_allowed, enabled_capabilities?}`` →
  ``{id, slug, label, write_allowed, capabilities, state, sockets}``.
- ``list``: ``{}`` → ``{integrations: [...]}``. Non-secret metadata of
  every active integration.
- ``resolve``: ``{id, capability}`` → ``{id, socket, write_allowed}``. The app server's
  broker_client calls this to locate a broker before any tool call.
- ``update``: ``{id, write_allowed?, label?}`` → the same record shape as
  ``add``. At least one of ``write_allowed`` / ``label`` must be present.
  ``label`` is meta-only (broker never sees it), so a label-only update
  rewrites meta in place. ``write_allowed`` flips the broker's env gate,
  so changing it terminates the broker and re-spawns with new env.
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
        if verb == "reauth_init":
            return await self._reauth_init(args)
        if verb == "reauth_verify":
            return await self._reauth_verify(args)
        msg = f"unknown verb: {verb}"
        raise RpcError("BAD_REQUEST", msg)

    # --- verbs --------------------------------------------------------------

    async def _add(self, args: dict[str, Any]) -> dict[str, Any]:
        enabled_capabilities: list[str] | None = None
        if "enabled_capabilities" in args:
            ec = args["enabled_capabilities"]
            if not isinstance(ec, list) or not all(isinstance(c, str) for c in ec):
                raise RpcError("BAD_REQUEST", "'enabled_capabilities' must be a list of strings")
            enabled_capabilities = ec
        
        record = await self._manager.add(
            slug=_require_str(args, "slug"),
            user_suffix=_require_str(args, "user_suffix"),
            label=_require_str(args, "label"),
            auth_blob=args.get("auth_blob"),
            write_allowed=bool(args.get("write_allowed", False)),
            enabled_capabilities=enabled_capabilities,
        )
        return _record_to_dict(record)

    def _list(self) -> dict[str, Any]:
        return {
            "integrations": [_record_to_dict(r) for r in self._registry.list()],
        }

    def _resolve(self, args: dict[str, Any]) -> dict[str, Any]:
        integration_id = _require_str(args, "id")
        capability = args.get("capability")
        record = self._registry.get(integration_id)
        if record is None:
            raise RpcError("NOT_FOUND", f"unknown integration: {integration_id}")
        
        if capability is None:
            # Default to first capability for backward compat
            capability = next(iter(record.brokers.keys()))
        
        if capability not in record.brokers:
            raise RpcError("NOT_FOUND", f"capability {capability!r} not available for {integration_id}")
        
        return {
            "id": record.meta.id,
            "socket": str(record.brokers[capability].socket_path),
            "write_allowed": record.meta.write_allowed,
        }

    async def _update(self, args: dict[str, Any]) -> dict[str, Any]:
        integration_id = _require_str(args, "id")
        write_allowed: bool | None = None
        if "write_allowed" in args:
            if not isinstance(args["write_allowed"], bool):
                raise RpcError("BAD_REQUEST", "'write_allowed' must be a bool")
            write_allowed = args["write_allowed"]
        label: str | None = None
        if "label" in args:
            if not isinstance(args["label"], str) or not args["label"]:
                raise RpcError("BAD_REQUEST", "'label' must be a non-empty string")
            label = args["label"]
        if write_allowed is None and label is None:
            raise RpcError(
                "BAD_REQUEST",
                "update requires 'write_allowed' and/or 'label'",
            )
        record = await self._manager.update(
            integration_id, write_allowed=write_allowed, label=label,
        )
        return _record_to_dict(record)

    async def _remove(self, args: dict[str, Any]) -> dict[str, Any]:
        integration_id = _require_str(args, "id")
        await self._manager.remove(integration_id)
        return {"id": integration_id}

    async def _reauth_init(self, args: dict[str, Any]) -> dict[str, Any]:
        integration_id = _require_str(args, "id")
        return await self._manager.reauth_init(integration_id)

    async def _reauth_verify(self, args: dict[str, Any]) -> dict[str, Any]:
        integration_id = _require_str(args, "id")
        session_id = _require_str(args, "session_id")
        code = _require_str(args, "code")
        record = await self._manager.reauth_verify(integration_id, session_id, code)
        return _record_to_dict(record)


def _record_to_dict(record) -> dict[str, Any]:
    """Wire-shape for one integration — used by ``add`` and ``list``."""
    # Build sockets dict mapping capability -> socket path
    sockets = {cap: str(handle.socket_path) for cap, handle in record.brokers.items()}
    
    result = {
        "id": record.meta.id,
        "slug": record.meta.slug,
        "label": record.meta.label,
        "write_allowed": record.meta.write_allowed,
        "capabilities": sorted(record.capabilities),
        "state": record.state,
        "sockets": sockets,
    }
    
    # Backward-compat: keep "socket" field pointing to the first broker's socket
    if record.brokers:
        first_cap = next(iter(record.brokers.keys()))
        result["socket"] = str(record.brokers[first_cap].socket_path)
    
    return result


def _require_str(args: dict[str, Any], key: str) -> str:
    """Extract a required string arg or raise BAD_REQUEST."""
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise RpcError("BAD_REQUEST", f"{key!r} required (non-empty string)")
    return value
