"""``app.sock`` RPC handler: ``add`` / ``list`` / ``resolve`` / ``remove``.

The app server (UID ``computron``) is the only legitimate client. Per the
broker RPC framing, requests are length-prefixed JSON frames with
``{id, verb, args}`` and responses are ``{id, result | error}``. Verbs and
their payloads:

- ``add``: ``{slug, user_suffix, label, auth_blob, write_allowed}`` →
  ``{id, socket}``. Writes vault files, spawns broker(s), registers them.
  Distinguishes auth-failure at spawn time (broker exits 77) from other
  spawn errors so the app server can surface the right message.
- ``list``: ``{}`` → ``{integrations: [...]}``. Non-secret metadata of
  every active integration. No crypto touched.
- ``resolve``: ``{id}`` → ``{id, socket, write_allowed}``. The app server's
  broker_client calls this to locate a broker before any tool call.
- ``remove``: ``{id}`` → ``{id}``. SIGTERMs brokers, deletes vault files.

Errors use the shared ``RpcError`` machinery: the RPC layer turns them into
``{error: {code, message}}`` frames.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from integrations._rpc import RpcError
from integrations.supervisor._catalog import CatalogEntry
from integrations.supervisor._registry import IntegrationRecord, Registry
from integrations.supervisor._spawn import BrokerSpawnError, spawn_broker
from integrations.supervisor._store import delete_integration, write_meta, write_secrets
from integrations.supervisor.types import IntegrationMeta

logger = logging.getLogger(__name__)

# Integration IDs use [a-z0-9_-]+ up to 64 chars; enforced here so malformed
# values never reach the filesystem as partial filenames.
_SUFFIX_PATTERN = re.compile(r"^[a-z0-9_-]{1,48}$")
_SHUTDOWN_GRACE_SECONDS = 5.0


class AppSockHandler:
    """Stateful verb router — the glue between catalog, store, spawn, and registry."""

    def __init__(
        self,
        *,
        vault_dir: Path,
        sockets_dir: Path,
        master_key: bytes,
        catalog: dict[str, CatalogEntry],
        registry: Registry,
    ) -> None:
        self._vault_dir = vault_dir
        self._sockets_dir = sockets_dir
        self._master_key = master_key
        self._catalog = catalog
        self._registry = registry

    async def handle(self, verb: str, args: dict[str, Any]) -> dict[str, Any]:
        """Entry point called by the RPC layer for every incoming frame."""
        if verb == "add":
            return await self._add(args)
        if verb == "list":
            return self._list()
        if verb == "resolve":
            return self._resolve(args)
        if verb == "remove":
            return await self._remove(args)
        msg = f"unknown verb: {verb}"
        raise RpcError("BAD_REQUEST", msg)

    # --- verbs --------------------------------------------------------------

    async def _add(self, args: dict[str, Any]) -> dict[str, Any]:
        slug = _require_str(args, "slug")
        user_suffix = _require_str(args, "user_suffix")
        label = _require_str(args, "label")
        auth_blob = args.get("auth_blob")
        write_allowed = bool(args.get("write_allowed", False))

        if slug not in self._catalog:
            raise RpcError("BAD_REQUEST", f"unknown slug: {slug}")
        if not _SUFFIX_PATTERN.match(user_suffix):
            raise RpcError(
                "BAD_REQUEST",
                "user_suffix must match [a-z0-9_-]{1,48}",
            )
        if not isinstance(auth_blob, dict):
            raise RpcError("BAD_REQUEST", "auth_blob must be a dict")

        entry = self._catalog[slug]
        integration_id = f"{slug}_{user_suffix}"
        if self._registry.contains(integration_id):
            raise RpcError("BAD_REQUEST", f"integration already exists: {integration_id}")

        now = datetime.now(UTC)
        meta = IntegrationMeta(
            id=integration_id,
            slug=slug,
            label=label,
            write_allowed=write_allowed,
            added_at=now,
            updated_at=now,
        )

        # Write vault files first. A crash between here and the spawn leaves
        # orphaned meta/enc on disk; startup reconciliation (later phase) handles
        # those. Better than orphaning a running broker without persisted state.
        write_meta(self._vault_dir, meta)
        write_secrets(self._vault_dir, integration_id, self._master_key, auth_blob)

        try:
            handle = await spawn_broker(
                entry=entry,
                integration_id=integration_id,
                secret_bundle=auth_blob,
                write_allowed=write_allowed,
                sockets_dir=self._sockets_dir,
            )
        except BrokerSpawnError as exc:
            # Roll back on spawn failure: delete the vault files we wrote. No
            # broker subprocess is running at this point (spawn either never
            # started the child, or the child already exited before READY).
            delete_integration(self._vault_dir, integration_id)
            if exc.exit_code == 77:
                raise RpcError("AUTH", "upstream rejected credentials") from exc
            raise RpcError("UPSTREAM", f"broker spawn failed: {exc}") from exc

        record = IntegrationRecord(meta=meta, broker=handle)
        self._registry.add(record)
        logger.info("added integration %s (slug=%s)", integration_id, slug)
        return {
            "id": integration_id,
            "slug": slug,
            "label": label,
            "write_allowed": write_allowed,
            "capabilities": sorted(entry.capabilities),
            "socket": str(handle.socket_path),
        }

    def _list(self) -> dict[str, Any]:
        return {
            "integrations": [
                {
                    "id": r.meta.id,
                    "slug": r.meta.slug,
                    "label": r.meta.label,
                    "write_allowed": r.meta.write_allowed,
                    "capabilities": sorted(self._catalog[r.meta.slug].capabilities),
                    "socket": str(r.broker.socket_path),
                }
                for r in self._registry.list()
            ],
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

    async def _remove(self, args: dict[str, Any]) -> dict[str, Any]:
        integration_id = _require_str(args, "id")
        record = self._registry.remove(integration_id)
        if record is None:
            raise RpcError("NOT_FOUND", f"unknown integration: {integration_id}")

        # Try graceful SIGTERM first; fall back to SIGKILL if the broker ignores it.
        handle = record.broker
        if handle.proc.returncode is None:
            handle.proc.terminate()
        try:
            await asyncio.wait_for(handle.proc.wait(), timeout=_SHUTDOWN_GRACE_SECONDS)
        except TimeoutError:
            handle.proc.kill()
            await handle.proc.wait()

        delete_integration(self._vault_dir, integration_id)
        logger.info("removed integration %s", integration_id)
        return {"id": integration_id}


def _require_str(args: dict[str, Any], key: str) -> str:
    """Extract a required string arg or raise BAD_REQUEST."""
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise RpcError("BAD_REQUEST", f"{key!r} required (non-empty string)")
    return value
