"""Centralized lifecycle for broker subprocesses.

One :class:`BrokerManager` per :class:`Supervisor` instance owns *every*
spawn path:

- ``add`` — user-driven new integration (vault is fresh, secrets come
  from the request body).
- ``reconcile_existing`` — boot-time rehydrate (vault has the meta + enc;
  decrypt then spawn).
- crash respawn — automatic restart with exponential backoff after an
  unexpected broker exit.

Each running broker has a watcher task awaiting its subprocess. Two
terminal states stop the watcher's respawn loop:

- ``auth_failed`` — broker exits with code 77 (upstream rejected creds).
  Hammering the upstream's auth endpoint risks rate-limit penalties; the
  user's recovery path is remove + re-add.
- ``broken`` — three consecutive failed respawns before READY. Likely a
  config bug or dead network path. Same recovery.

Vault I/O, catalog lookups, and ``spawn_broker`` calls all live behind
this manager. The RPC handler (``AppSockHandler``) becomes a thin
dispatcher; the supervisor lifecycle (``Supervisor.start`` / ``stop``)
owns the manager and orchestrates startup ordering.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from integrations._rpc import RpcError
from integrations.supervisor._catalog import CatalogEntry
from integrations.supervisor._crypto import DecryptError
from integrations.supervisor._registry import IntegrationRecord, Registry
from integrations.supervisor._spawn import BrokerHandle, BrokerSpawnError, spawn_broker
from integrations.supervisor._store import (
    delete_integration,
    read_meta,
    read_secrets,
    write_meta,
    write_secrets,
)
from integrations.supervisor.types import IntegrationMeta

logger = logging.getLogger(__name__)

# Integration IDs use [a-z0-9_-]+ up to 64 chars; enforced here so malformed
# values never reach the filesystem as partial filenames.
_SUFFIX_PATTERN = re.compile(r"^[a-z0-9_-]{1,48}$")
_SHUTDOWN_GRACE_SECONDS = 5.0

# Exponential backoff between respawn attempts: 1s, 2s, 4s, 8s, 16s, 30s cap.
_BACKOFF_BASE_SECONDS = 1.0
_BACKOFF_CAP_SECONDS = 30.0

# How many consecutive failed respawns before giving up and marking "broken".
_MAX_CONSECUTIVE_FAILURES = 3

# Broker exit code that means "upstream rejected the credentials" — the value
# brokers' __main__ uses for ImapAuthError / similar. Hardcoded here to avoid
# importing across the broker package boundary.
_AUTH_FAIL_EXIT_CODE = 77


class BrokerManager:
    """Owns spawn / watch / respawn / remove for every broker."""

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
        self._watchers: dict[str, asyncio.Task[None]] = {}

    # --- public lifecycle ---------------------------------------------------

    async def add(
        self,
        *,
        slug: str,
        user_suffix: str,
        label: str,
        auth_blob: dict,
        write_allowed: bool,
    ) -> IntegrationRecord:
        """Register a brand-new integration: validate, persist, spawn, watch.

        Raises :class:`RpcError` on validation failure or spawn failure;
        the handler propagates straight through.
        """
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

        # Write vault first. A crash between here and the spawn leaves orphaned
        # files on disk; ``reconcile_existing`` picks them up on the next boot.
        # Better than orphaning a running broker without persisted state.
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
            # Roll back — no broker subprocess is running at this point.
            delete_integration(self._vault_dir, integration_id)
            if exc.exit_code == _AUTH_FAIL_EXIT_CODE:
                raise RpcError("AUTH", "upstream rejected credentials") from exc
            raise RpcError("UPSTREAM", f"broker spawn failed: {exc}") from exc

        record = IntegrationRecord(
            meta=meta,
            broker=handle,
            capabilities=frozenset(entry.capabilities),
        )
        self._registry.add(record)
        self._start_watcher(integration_id)
        logger.info("added integration %s (slug=%s)", integration_id, slug)
        return record

    async def reconcile_existing(self, integration_id: str) -> IntegrationRecord:
        """Re-spawn a broker for an integration already persisted in the vault.

        Raises :class:`ReconcileError` on any failure path so the caller
        (Supervisor.start) can log and skip a single bad integration without
        bringing the whole supervisor down.
        """
        meta = read_meta(self._vault_dir, integration_id)
        entry = self._catalog.get(meta.slug)
        if entry is None:
            msg = f"catalog has no entry for slug {meta.slug!r}"
            raise ReconcileError(msg)

        try:
            secret_bundle = read_secrets(self._vault_dir, integration_id, self._master_key)
        except DecryptError as exc:
            msg = f"decrypt failed for {integration_id}: {exc}"
            raise ReconcileError(msg) from exc

        try:
            handle = await spawn_broker(
                entry=entry,
                integration_id=integration_id,
                secret_bundle=secret_bundle,
                write_allowed=meta.write_allowed,
                sockets_dir=self._sockets_dir,
            )
        except BrokerSpawnError as exc:
            kind = "auth rejected" if exc.exit_code == _AUTH_FAIL_EXIT_CODE else "spawn failed"
            msg = f"{kind} for {integration_id}: {exc}"
            raise ReconcileError(msg) from exc

        record = IntegrationRecord(
            meta=meta,
            broker=handle,
            capabilities=frozenset(entry.capabilities),
        )
        self._registry.add(record)
        self._start_watcher(integration_id)
        logger.info("reconciled %s (slug=%s)", integration_id, meta.slug)
        return record

    async def remove(self, integration_id: str) -> None:
        """Tear down an integration: stop watcher, SIGTERM, drop registry, wipe vault.

        Raises :class:`RpcError` (NOT_FOUND) if the id isn't registered.
        """
        record = self._registry.get(integration_id)
        if record is None:
            raise RpcError("NOT_FOUND", f"unknown integration: {integration_id}")

        # Flag the record first so the watcher sees expected_termination on
        # the next iteration (or already-pending wait), then cancel its task
        # so the SIGTERM below isn't read as a crash.
        record.expected_termination = True
        watcher = self._watchers.pop(integration_id, None)
        if watcher is not None and not watcher.done():
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)

        self._registry.remove(integration_id)
        await self._terminate_broker(record.broker)
        delete_integration(self._vault_dir, integration_id)
        logger.info("removed integration %s", integration_id)

    async def update(
        self, integration_id: str, *, write_allowed: bool,
    ) -> IntegrationRecord:
        """Flip the ``write_allowed`` policy on an existing integration.

        The broker reads ``WRITE_ALLOWED`` from its env at spawn time, so a
        flip means: rewrite the on-disk meta, terminate the running broker,
        then re-spawn it with the new env. There's a brief gap (~SIGTERM
        grace + READY handshake) during which the broker socket is gone.

        Raises :class:`RpcError` (NOT_FOUND) if the id isn't registered.
        Returns the updated record on success. If the respawn fails, the
        meta on disk has the new value and the in-memory record is marked
        ``broken``; the caller's recovery path is remove + re-add.
        """
        record = self._registry.get(integration_id)
        if record is None:
            raise RpcError("NOT_FOUND", f"unknown integration: {integration_id}")

        # No-op shortcut: nothing to do, no respawn cost incurred.
        if record.meta.write_allowed == write_allowed:
            return record

        entry = self._catalog.get(record.meta.slug)
        if entry is None:
            # The slug existed when the integration was added but no longer
            # does — same shape as the reconcile path's catalog-drift error.
            raise RpcError(
                "BAD_REQUEST",
                f"catalog has no entry for slug {record.meta.slug!r}",
            )

        try:
            secret_bundle = read_secrets(
                self._vault_dir, integration_id, self._master_key,
            )
        except DecryptError as exc:
            raise RpcError("INTERNAL", f"decrypt failed: {exc}") from exc

        new_meta = record.meta.model_copy(
            update={"write_allowed": write_allowed, "updated_at": datetime.now(UTC)},
        )
        # Commit the meta change before we touch the running process. If we
        # crash between this write and the respawn, the next reconcile
        # picks up the new value.
        write_meta(self._vault_dir, new_meta)

        # Stop the watcher and terminate before respawn — same dance as
        # remove(), but we keep the registry entry so the new handle slots
        # back in under the same id.
        record.expected_termination = True
        watcher = self._watchers.pop(integration_id, None)
        if watcher is not None and not watcher.done():
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
        await self._terminate_broker(record.broker)

        try:
            new_handle = await spawn_broker(
                entry=entry,
                integration_id=integration_id,
                secret_bundle=secret_bundle,
                write_allowed=write_allowed,
                sockets_dir=self._sockets_dir,
            )
        except BrokerSpawnError as exc:
            # New meta is on disk, but we have no live broker. Mark broken
            # so list/resolve surface the failure; user remediation is
            # remove + re-add.
            record.state = "broken"
            if exc.exit_code == _AUTH_FAIL_EXIT_CODE:
                record.state = "auth_failed"
                raise RpcError("AUTH", "upstream rejected credentials") from exc
            raise RpcError("UPSTREAM", f"broker respawn failed: {exc}") from exc

        # Reset terminal-state flags now that the new broker is live.
        record.broker = new_handle
        record.meta = new_meta
        record.state = "running"
        record.expected_termination = False
        self._start_watcher(integration_id)
        logger.info(
            "updated integration %s (write_allowed=%s)",
            integration_id, write_allowed,
        )
        return record

    async def stop_all(self) -> None:
        """Supervisor shutdown: stop all watchers, then SIGTERM all brokers."""
        for record in self._registry.list():
            record.expected_termination = True

        watchers = list(self._watchers.values())
        for task in watchers:
            task.cancel()
        if watchers:
            await asyncio.gather(*watchers, return_exceptions=True)
        self._watchers.clear()

        for record in self._registry.list():
            await self._terminate_broker(record.broker)

    # --- internals ----------------------------------------------------------

    def _start_watcher(self, integration_id: str) -> None:
        """Schedule the per-broker watcher. Idempotent: replaces an existing one."""
        existing = self._watchers.get(integration_id)
        if existing is not None and not existing.done():
            existing.cancel()
        self._watchers[integration_id] = asyncio.create_task(
            self._watch(integration_id),
            name=f"broker-watch-{integration_id}",
        )

    async def _terminate_broker(self, handle: BrokerHandle) -> None:
        """SIGTERM with grace; SIGKILL if the broker ignores us."""
        if handle.proc.returncode is None:
            handle.proc.terminate()
        try:
            await asyncio.wait_for(handle.proc.wait(), timeout=_SHUTDOWN_GRACE_SECONDS)
        except TimeoutError:
            handle.proc.kill()
            await handle.proc.wait()

    async def _watch(self, integration_id: str) -> None:
        """Per-broker respawn loop with exponential backoff and circuit-breakers."""
        consecutive_failures = 0
        while True:
            record = self._registry.get(integration_id)
            if record is None:
                return

            try:
                exit_code = await record.broker.proc.wait()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "watcher for %s failed waiting on broker", integration_id,
                )
                return

            record = self._registry.get(integration_id)
            if record is None or record.expected_termination:
                return

            logger.warning(
                "broker for %s exited unexpectedly (code=%s); attempting respawn",
                integration_id, exit_code,
            )

            if exit_code == _AUTH_FAIL_EXIT_CODE:
                logger.warning(
                    "broker for %s exited with auth-fail code %d; "
                    "marking auth_failed and stopping respawn",
                    integration_id, exit_code,
                )
                record.state = "auth_failed"
                return

            consecutive_failures += 1
            if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                logger.warning(
                    "broker for %s failed %d times in a row; marking broken",
                    integration_id, consecutive_failures,
                )
                record.state = "broken"
                return

            backoff = min(
                _BACKOFF_CAP_SECONDS,
                _BACKOFF_BASE_SECONDS * (2 ** (consecutive_failures - 1)),
            )
            logger.info(
                "respawning broker for %s in %.1fs (attempt %d)",
                integration_id, backoff, consecutive_failures,
            )
            await asyncio.sleep(backoff)

            try:
                new_handle = await self._respawn(integration_id, record)
            except _RespawnError as exc:
                logger.warning("respawn failed for %s: %s", integration_id, exc)
                if exc.exit_code == _AUTH_FAIL_EXIT_CODE:
                    record.state = "auth_failed"
                    return
                continue

            record.broker = new_handle
            record.state = "running"
            consecutive_failures = 0
            logger.info("respawned broker for %s", integration_id)

    async def _respawn(
        self, integration_id: str, record: IntegrationRecord,
    ) -> BrokerHandle:
        """Read secrets + spawn a fresh broker for an existing record."""
        entry = self._catalog.get(record.meta.slug)
        if entry is None:
            msg = f"catalog has no entry for slug {record.meta.slug!r}"
            raise _RespawnError(msg)

        try:
            secret_bundle = read_secrets(self._vault_dir, integration_id, self._master_key)
        except DecryptError as exc:
            msg = f"decrypt failed: {exc}"
            raise _RespawnError(msg) from exc

        try:
            return await spawn_broker(
                entry=entry,
                integration_id=integration_id,
                secret_bundle=secret_bundle,
                write_allowed=record.meta.write_allowed,
                sockets_dir=self._sockets_dir,
            )
        except BrokerSpawnError as exc:
            raise _RespawnError(str(exc), exit_code=exc.exit_code) from exc


class ReconcileError(Exception):
    """Reconciliation of one integration failed.

    Causes are catalog drift (slug removed since registration), decrypt
    error, or spawn failure (auth rejected, READY timeout, etc.). The
    supervisor logs and skips, leaving the vault files intact so the
    user can recover via remove + re-add.
    """


class _RespawnError(Exception):
    """Internal — wraps any failure inside :meth:`BrokerManager._respawn`."""

    def __init__(self, message: str, *, exit_code: int | None = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code
