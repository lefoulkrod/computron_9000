"""``app.sock`` RPC handler.

The app server (UID ``computron``) is the only legitimate client. Requests
and responses use the shared length-prefixed JSON framing.

Verbs
-----

**add** (slug, user_suffix, label, auth_blob, permissions)
    Encrypt credentials, spawn a broker, return the new record.
    Both the app-password and OAuth add flows end here.

**list** ()
    Non-secret metadata for every active integration.

**resolve** (id)
    Look up a broker's UDS path by integration ID. Called by the
    broker_client before every tool invocation.

**update** (id, permissions?, label?)
    Change permissions and/or label on a live integration. At least one
    field required. Label changes are meta-only; permission changes
    respawn the broker so the new env takes effect.

**remove** (id)
    SIGTERM the broker and delete its vault files.

The handler is a thin dispatcher: it parses args and delegates to a
:class:`BrokerManager` (lifecycle) and :class:`Registry` (read access).
"""

from __future__ import annotations

import logging
from typing import Any

from integrations._rpc import RpcError
from integrations.permissions import (
    access_to_str,
    permissions_from_dict,
    permissions_to_dict,
)
from integrations.supervisor._manager import BrokerManager
from integrations.supervisor._registry import IntegrationRecord, Registry

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
        perms_raw = args.get("permissions")
        if not isinstance(perms_raw, dict):
            raise RpcError("BAD_REQUEST", "'permissions' required (dict)")
        record = await self._manager.add(
            slug=_require_str(args, "slug"),
            user_suffix=args.get("user_suffix") or None,
            label=_require_str(args, "label"),
            auth_blob=args.get("auth_blob"),
            permissions=permissions_from_dict(perms_raw),
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
            "permissions": permissions_to_dict(record.meta.permissions),
        }

    async def _update(self, args: dict[str, Any]) -> dict[str, Any]:
        integration_id = _require_str(args, "id")
        permissions = None
        if "permissions" in args:
            perms_raw = args["permissions"]
            if not isinstance(perms_raw, dict):
                raise RpcError("BAD_REQUEST", "'permissions' must be a dict")
            permissions = permissions_from_dict(perms_raw)
        label: str | None = None
        if "label" in args:
            if not isinstance(args["label"], str) or not args["label"]:
                raise RpcError("BAD_REQUEST", "'label' must be a non-empty string")
            label = args["label"]
        if permissions is None and label is None:
            raise RpcError(
                "BAD_REQUEST",
                "update requires 'permissions' and/or 'label'",
            )
        record = await self._manager.update(
            integration_id, permissions=permissions, label=label,
        )
        return _record_to_dict(record)

    async def _remove(self, args: dict[str, Any]) -> dict[str, Any]:
        integration_id = _require_str(args, "id")
        await self._manager.remove(integration_id)
        return {"id": integration_id}


def _record_to_dict(record: IntegrationRecord) -> dict[str, Any]:
    """Wire-shape for one integration — used by ``add``, ``list``, ``update``."""
    return {
        "id": record.meta.id,
        "slug": record.meta.slug,
        "label": record.meta.label,
        "permissions": permissions_to_dict(record.meta.permissions),
        "max_access": {cap.value: access_to_str(a) for cap, a in record.max_access.items()},
        "capabilities": sorted(cap.value for cap in record.max_access),
        "state": record.state,
        "socket": str(record.broker.socket_path),
    }


def _require_str(args: dict[str, Any], key: str) -> str:
    """Extract a required string arg or raise BAD_REQUEST."""
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise RpcError("BAD_REQUEST", f"{key!r} required (non-empty string)")
    return value
