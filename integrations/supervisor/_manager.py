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
from typing import Any

from integrations._rpc import RpcError
from integrations.supervisor._catalog import BrokerSpec, CatalogEntry
from integrations.supervisor._crypto import DecryptError
from integrations.supervisor._registry import IntegrationRecord, Registry
from integrations.supervisor._spawn import BrokerHandle, BrokerSpawnError, spawn_broker
from integrations.supervisor.types import HostPath
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
        host_paths: dict[str, HostPath],
        master_key: bytes,
        catalog: dict[str, CatalogEntry],
        registry: Registry,
    ) -> None:
        self._vault_dir = vault_dir
        self._sockets_dir = sockets_dir
        self._host_paths = host_paths
        self._master_key = master_key
        self._catalog = catalog
        self._registry = registry
        # Watcher keys are (integration_id, capability) tuples
        self._watchers: dict[tuple[str, str], asyncio.Task[None]] = {}

    # --- public lifecycle ---------------------------------------------------

    async def add(
        self,
        *,
        slug: str,
        user_suffix: str,
        label: str,
        auth_blob: dict,
        write_allowed: bool,
        enabled_capabilities: list[str] | None = None,
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

        # Determine enabled capabilities
        all_capabilities = entry.capabilities
        if enabled_capabilities is None or len(enabled_capabilities) == 0:
            # Backward compat: default to all capabilities from catalog
            enabled_capabilities = sorted(all_capabilities)
        
        # Validate each capability exists in the catalog entry
        for cap in enabled_capabilities:
            if cap not in all_capabilities:
                raise RpcError(
                    "BAD_REQUEST",
                    f"capability {cap!r} not available for slug {slug!r}",
                )

        now = datetime.now(UTC)
        meta = IntegrationMeta(
            id=integration_id,
            slug=slug,
            label=label,
            write_allowed=write_allowed,
            enabled_capabilities=enabled_capabilities,
            added_at=now,
            updated_at=now,
        )

        # Write vault first. A crash between here and the spawn leaves orphaned
        # files on disk; ``reconcile_existing`` picks them up on the next boot.
        # Better than orphaning a running broker without persisted state.
        write_meta(self._vault_dir, meta)
        write_secrets(self._vault_dir, integration_id, self._master_key, auth_blob)

        # Spawn all brokers concurrently
        spawned_handles: dict[str, BrokerHandle] = {}
        spawn_errors: list[Exception] = []
        
        for cap in enabled_capabilities:
            spec = entry.broker_for(cap)
            try:
                handle = await spawn_broker(
                    spec=spec,
                    integration_id=integration_id,
                    secret_bundle=auth_blob,
                    write_allowed=write_allowed,
                    sockets_dir=self._sockets_dir,
                    host_paths=self._host_paths,
                )
                spawned_handles[cap] = handle
            except BrokerSpawnError as exc:
                spawn_errors.append((cap, exc))

        # If any spawn failed, roll back all spawned brokers and delete vault files
        if spawn_errors:
            # Terminate all successfully spawned brokers
            for handle in spawned_handles.values():
                await self._terminate_broker(handle)
            # Delete vault files
            delete_integration(self._vault_dir, integration_id)
            
            # Check if any were auth failures
            for cap, exc in spawn_errors:
                if exc.exit_code == _AUTH_FAIL_EXIT_CODE:
                    raise RpcError("AUTH", "upstream rejected credentials") from exc
            
            # Generic spawn failure
            first_cap, first_exc = spawn_errors[0]
            raise RpcError("UPSTREAM", f"broker spawn failed for {first_cap}: {first_exc}") from first_exc

        record = IntegrationRecord(
            meta=meta,
            brokers=spawned_handles,
            capabilities=frozenset(enabled_capabilities),
        )
        self._registry.add(record)
        
        # Start watchers for all capabilities
        for cap in enabled_capabilities:
            self._start_watcher(integration_id, cap)
        
        logger.info("added integration %s (slug=%s, capabilities=%s)", integration_id, slug, enabled_capabilities)
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

        # Determine enabled capabilities with backward compat
        if meta.version == 1 or not meta.enabled_capabilities:
            # Default to email_calendar for backward compat
            enabled_capabilities = ["email_calendar"]
        else:
            enabled_capabilities = meta.enabled_capabilities

        # Spawn all brokers
        spawned_handles: dict[str, BrokerHandle] = {}
        spawn_errors: list[tuple[str, BrokerSpawnError]] = []
        
        for cap in enabled_capabilities:
            spec = entry.broker_for(cap)
            try:
                handle = await spawn_broker(
                    spec=spec,
                    integration_id=integration_id,
                    secret_bundle=secret_bundle,
                    write_allowed=meta.write_allowed,
                    sockets_dir=self._sockets_dir,
                    host_paths=self._host_paths,
                )
                spawned_handles[cap] = handle
            except BrokerSpawnError as exc:
                spawn_errors.append((cap, exc))

        if spawn_errors:
            for handle in spawned_handles.values():
                await self._terminate_broker(handle)
            kind = "auth rejected" if any(e.exit_code == _AUTH_FAIL_EXIT_CODE for _, e in spawn_errors) else "spawn failed"
            first_cap, first_exc = spawn_errors[0]
            msg = f"{kind} for {integration_id} ({first_cap}): {first_exc}"
            raise ReconcileError(msg) from first_exc

        record = IntegrationRecord(
            meta=meta,
            brokers=spawned_handles,
            capabilities=frozenset(enabled_capabilities),
        )
        self._registry.add(record)
        
        for cap in enabled_capabilities:
            self._start_watcher(integration_id, cap)
        
        logger.info("reconciled %s (slug=%s, capabilities=%s)", integration_id, meta.slug, enabled_capabilities)
        return record

    async def remove(self, integration_id: str) -> None:
        """Tear down an integration: stop watchers, SIGTERM, drop registry, wipe vault.

        Raises :class:`RpcError` (NOT_FOUND) if the id isn't registered.
        """
        record = self._registry.get(integration_id)
        if record is None:
            raise RpcError("NOT_FOUND", f"unknown integration: {integration_id}")

        # Flag the record first so the watchers see expected_termination on
        # the next iteration (or already-pending wait), then cancel their tasks
        # so the SIGTERM below isn't read as a crash.
        record.expected_termination = True
        
        # Cancel all watchers for this integration
        caps_to_remove = list(record.brokers.keys())
        for cap in caps_to_remove:
            watcher = self._watchers.pop((integration_id, cap), None)
            if watcher is not None and not watcher.done():
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)

        self._registry.remove(integration_id)
        
        # Terminate all brokers
        for handle in record.brokers.values():
            await self._terminate_broker(handle)
        
        delete_integration(self._vault_dir, integration_id)
        logger.info("removed integration %s", integration_id)

    async def reauth_init(self, integration_id: str) -> dict[str, Any]:
        """Start re-authentication for an iCloud Drive integration.

        Reads the stored password from the vault and initiates a new SRP
        handshake with Apple.  Returns ``{session_id, requires_2fa}``.

        Raises :class:`RpcError` (NOT_FOUND) if the id isn't registered,
        or (INTERNAL) if the vault can't be read.
        """
        record = self._registry.get(integration_id)
        if record is None:
            raise RpcError("NOT_FOUND", f"unknown integration: {integration_id}")

        try:
            secret_bundle = read_secrets(self._vault_dir, integration_id, self._master_key)
        except DecryptError as exc:
            raise RpcError("INTERNAL", f"decrypt failed: {exc}") from exc

        password = secret_bundle.get("password")
        email = secret_bundle.get("email")
        if not isinstance(password, str) or not password:
            raise RpcError("INTERNAL", "no password in stored secrets")
        if not isinstance(email, str) or not email:
            raise RpcError("INTERNAL", "no email in stored secrets")

        from integrations._icloud_auth import (
            IcloudAuthError,
            IcloudAuthPasswordError,
            initiate_auth,
        )

        try:
            result = initiate_auth(email, password)
        except IcloudAuthPasswordError as exc:
            raise RpcError("AUTH", str(exc)) from exc
        except IcloudAuthError as exc:
            raise RpcError("UPSTREAM", str(exc)) from exc

        return result

    async def reauth_verify(
        self, integration_id: str, session_id: str, code: str,
    ) -> IntegrationRecord:
        """Complete re-authentication: validate 2FA code, write new trust token, respawn.

        Returns the updated :class:`IntegrationRecord` on success.

        Raises :class:`RpcError` (AUTH) if the code is wrong or the session
        expired, or (UPSTREAM) if the broker fails to respawn.
        """
        record = self._registry.get(integration_id)
        if record is None:
            raise RpcError("NOT_FOUND", f"unknown integration: {integration_id}")

        from integrations._icloud_auth import IcloudAuthError, complete_auth

        try:
            complete_auth(session_id, code)
        except IcloudAuthError as exc:
            raise RpcError("AUTH", str(exc)) from exc

        # Respawn the storage broker with the new trust token
        entry = self._catalog.get(record.meta.slug)
        if entry is None:
            raise RpcError("INTERNAL", f"catalog has no entry for slug {record.meta.slug!r}")

        try:
            secret_bundle = read_secrets(self._vault_dir, integration_id, self._master_key)
        except DecryptError as exc:
            raise RpcError("INTERNAL", f"decrypt failed: {exc}") from exc

        # Stop existing watcher and terminate old broker if still running
        cap = "storage"
        watcher = self._watchers.pop((integration_id, cap), None)
        if watcher is not None and not watcher.done():
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)

        old_handle = record.brokers.get(cap)
        if old_handle is not None and old_handle.proc.returncode is None:
            record.expected_termination = True
            await self._terminate_broker(old_handle)

        # Spawn fresh broker
        spec = entry.broker_for(cap)
        try:
            new_handle = await spawn_broker(
                spec=spec,
                integration_id=integration_id,
                secret_bundle=secret_bundle,
                write_allowed=record.meta.write_allowed,
                sockets_dir=self._sockets_dir,
                host_paths=self._host_paths,
            )
        except BrokerSpawnError as exc:
            record.state = "auth_failed" if exc.exit_code == _AUTH_FAIL_EXIT_CODE else "broken"
            raise RpcError("UPSTREAM", f"broker respawn failed: {exc}") from exc

        record.brokers[cap] = new_handle
        record.state = "running"
        record.expected_termination = False
        self._start_watcher(integration_id, cap)

        logger.info("reauth complete for %s", integration_id)
        return record

    async def update(
        self,
        integration_id: str,
        *,
        write_allowed: bool | None = None,
        label: str | None = None,
    ) -> IntegrationRecord:
        """Update mutable fields on an existing integration.

        Mutables today are ``write_allowed`` and ``label``. Both are
        optional — pass only the fields that should change. ``label`` is a
        string the broker never sees, so a label-only update rewrites the
        meta on disk and that's it. ``write_allowed`` is read from the
        broker's env at spawn time, so flipping it means rewrite + SIGTERM
        + respawn with the new env (brief gap during which the broker
        socket is gone).

        Raises :class:`RpcError` (NOT_FOUND) if the id isn't registered.
        Returns the updated record on success. If the respawn fails, the
        meta on disk has the new value and the in-memory record is marked
        ``broken``; the caller's recovery path is remove + re-add.
        """
        record = self._registry.get(integration_id)
        if record is None:
            raise RpcError("NOT_FOUND", f"unknown integration: {integration_id}")

        if write_allowed is None and label is None:
            raise RpcError("BAD_REQUEST", "update requires at least one field")

        if label is not None and not label:
            raise RpcError("BAD_REQUEST", "'label' must be a non-empty string")

        write_changed = (
            write_allowed is not None and record.meta.write_allowed != write_allowed
        )
        label_changed = label is not None and record.meta.label != label

        # No-op shortcut: nothing actually different, skip the work.
        if not write_changed and not label_changed:
            return record

        meta_updates: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if write_changed:
            meta_updates["write_allowed"] = write_allowed
        if label_changed:
            meta_updates["label"] = label
        new_meta = record.meta.model_copy(update=meta_updates)
        # Commit the meta change before we touch the running process. If we
        # crash between this write and a respawn, the next reconcile picks
        # up the new value.
        write_meta(self._vault_dir, new_meta)

        # Label-only: no env change, no respawn. Update in place and return.
        if not write_changed:
            record.meta = new_meta
            logger.info("updated integration %s (label=%r)", integration_id, label)
            return record

        # write_allowed changed — all brokers need a new env, which means respawn all.
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

        # Stop all watchers and terminate all brokers before respawn
        record.expected_termination = True
        for cap in list(record.brokers.keys()):
            watcher = self._watchers.pop((integration_id, cap), None)
            if watcher is not None and not watcher.done():
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)
        
        for handle in record.brokers.values():
            await self._terminate_broker(handle)

        # Respawn all brokers
        new_handles: dict[str, BrokerHandle] = {}
        spawn_errors: list[tuple[str, BrokerSpawnError]] = []
        
        for cap in record.capabilities:
            spec = entry.broker_for(cap)
            try:
                handle = await spawn_broker(
                    spec=spec,
                    integration_id=integration_id,
                    secret_bundle=secret_bundle,
                    write_allowed=new_meta.write_allowed,
                    sockets_dir=self._sockets_dir,
                    host_paths=self._host_paths,
                )
                new_handles[cap] = handle
            except BrokerSpawnError as exc:
                spawn_errors.append((cap, exc))

        if spawn_errors:
            # Terminate any successfully spawned brokers
            for handle in new_handles.values():
                await self._terminate_broker(handle)
            # Mark broken
            record.state = "broken"
            for cap, exc in spawn_errors:
                if exc.exit_code == _AUTH_FAIL_EXIT_CODE:
                    record.state = "auth_failed"
                    raise RpcError("AUTH", "upstream rejected credentials") from exc
            first_cap, first_exc = spawn_errors[0]
            raise RpcError("UPSTREAM", f"broker respawn failed for {first_cap}: {first_exc}") from first_exc

        # Reset terminal-state flags now that all new brokers are live.
        record.brokers = new_handles
        record.meta = new_meta
        record.state = "running"
        record.expected_termination = False
        
        # Restart all watchers
        for cap in record.capabilities:
            self._start_watcher(integration_id, cap)
        
        logger.info(
            "updated integration %s (write_allowed=%s, label=%r)",
            integration_id, new_meta.write_allowed, new_meta.label,
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
            for handle in record.brokers.values():
                await self._terminate_broker(handle)

    # --- internals ----------------------------------------------------------

    def _start_watcher(self, integration_id: str, capability: str) -> None:
        """Schedule the per-broker watcher. Idempotent: replaces an existing one."""
        key = (integration_id, capability)
        existing = self._watchers.get(key)
        if existing is not None and not existing.done():
            existing.cancel()
        self._watchers[key] = asyncio.create_task(
            self._watch(integration_id, capability),
            name=f"broker-watch-{integration_id}-{capability}",
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

    async def _watch(self, integration_id: str, capability: str) -> None:
        """Per-broker respawn loop with exponential backoff and circuit-breakers."""
        consecutive_failures = 0
        while True:
            record = self._registry.get(integration_id)
            if record is None:
                return

            handle = record.brokers.get(capability)
            if handle is None:
                return

            try:
                exit_code = await handle.proc.wait()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "watcher for %s (%s) failed waiting on broker", integration_id, capability,
                )
                return

            record = self._registry.get(integration_id)
            if record is None or record.expected_termination:
                return

            logger.warning(
                "broker for %s (%s) exited unexpectedly (code=%s); attempting respawn",
                integration_id, capability, exit_code,
            )

            if exit_code == _AUTH_FAIL_EXIT_CODE:
                logger.warning(
                    "broker for %s (%s) exited with auth-fail code %d; "
                    "marking auth_failed and stopping respawn",
                    integration_id, capability, exit_code,
                )
                record.state = "auth_failed"
                return

            consecutive_failures += 1
            if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                logger.warning(
                    "broker for %s (%s) failed %d times in a row; marking broken",
                    integration_id, capability, consecutive_failures,
                )
                record.state = "broken"
                return

            backoff = min(
                _BACKOFF_CAP_SECONDS,
                _BACKOFF_BASE_SECONDS * (2 ** (consecutive_failures - 1)),
            )
            logger.info(
                "respawning broker for %s (%s) in %.1fs (attempt %d)",
                integration_id, capability, backoff, consecutive_failures,
            )
            await asyncio.sleep(backoff)

            try:
                new_handle = await self._respawn(integration_id, capability, record)
            except _RespawnError as exc:
                logger.warning("respawn failed for %s (%s): %s", integration_id, capability, exc)
                if exc.exit_code == _AUTH_FAIL_EXIT_CODE:
                    record.state = "auth_failed"
                    return
                continue

            record.brokers[capability] = new_handle
            record.state = "running"
            consecutive_failures = 0
            logger.info("respawned broker for %s (%s)", integration_id, capability)

    async def _respawn(
        self, integration_id: str, capability: str, record: IntegrationRecord,
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

        spec = entry.broker_for(capability)
        try:
            return await spawn_broker(
                spec=spec,
                integration_id=integration_id,
                secret_bundle=secret_bundle,
                write_allowed=record.meta.write_allowed,
                sockets_dir=self._sockets_dir,
                host_paths=self._host_paths,
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
