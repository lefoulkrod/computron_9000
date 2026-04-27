"""Top-level supervisor lifecycle: master key, registry, app.sock listener.

The :class:`Supervisor` class is what tests instantiate and what ``__main__``
will eventually wire up. It doesn't run a loop itself — the caller awaits
``start()``, does its work (or blocks on ``serve_forever`` in production), then
awaits ``stop()``.

Broker lifecycle (spawn / watch / respawn / remove) lives in
:class:`integrations.supervisor._manager.BrokerManager`. The supervisor
orchestrates startup ordering — bind the listener AFTER reconciliation so
clients never see a half-warmed registry — and delegates everything
broker-shaped to the manager.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from integrations._rpc import serve_rpc
from integrations.supervisor._app_sock import AppSockHandler
from integrations.supervisor._catalog import CatalogEntry, validate_host_path_bindings
from integrations.supervisor._crypto import load_or_init_master_key
from integrations.supervisor._manager import BrokerManager, ReconcileError
from integrations.supervisor._registry import Registry
from integrations.supervisor._store import list_integration_ids
from integrations.supervisor.types import HostPath

logger = logging.getLogger(__name__)


class Supervisor:
    """Owns the vault, the registry, the broker manager, and the ``app.sock`` listener.

    Normal lifecycle::

        sup = Supervisor(vault_dir=..., app_sock_path=..., sockets_dir=...)
        await sup.start()
        try:
            # production: run until signal; tests: do work
            ...
        finally:
            await sup.stop()

    All paths are configurable so tests can point at ``tmp_path`` without env
    wrangling. ``catalog`` is required — production callers pass the project's
    ``DEFAULT_CATALOG`` explicitly; tests pass an injected catalog with broker
    specs pointed at fake upstream ports. Not making this implicit keeps a
    forgotten argument from silently using the production catalog in tests.
    """

    def __init__(
        self,
        *,
        vault_dir: Path,
        app_sock_path: Path,
        sockets_dir: Path,
        host_paths: dict[str, HostPath],
        catalog: dict[str, CatalogEntry],
    ) -> None:
        self.vault_dir = vault_dir
        self.app_sock_path = app_sock_path
        self.sockets_dir = sockets_dir
        self.host_paths = host_paths
        self.catalog = catalog

        self._master_key: bytes | None = None
        self._registry: Registry | None = None
        self._manager: BrokerManager | None = None
        self._handler: AppSockHandler | None = None
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        """Initialize vault, master key, manager; rehydrate brokers; bind ``app.sock``.

        Reconciliation runs before the listener binds so the supervisor
        doesn't serve ``list`` / ``resolve`` requests while brokers are
        still mid-respawn — first reader sees a fully-warmed registry.
        """
        # Catalog/registry agreement is checked up front so a typo in a
        # catalog entry's host_paths fails the boot rather than the first
        # spawn for that slug.
        validate_host_path_bindings(self.catalog, self.host_paths)

        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.sockets_dir.mkdir(parents=True, exist_ok=True)

        self._master_key = load_or_init_master_key(self.vault_dir)
        self._registry = Registry()
        self._manager = BrokerManager(
            vault_dir=self.vault_dir,
            sockets_dir=self.sockets_dir,
            host_paths=self.host_paths,
            master_key=self._master_key,
            catalog=self.catalog,
            registry=self._registry,
        )

        await self._reconcile_from_disk()

        self._handler = AppSockHandler(
            manager=self._manager,
            registry=self._registry,
        )
        self._server = await serve_rpc(self.app_sock_path, self._handler.handle)
        logger.info("supervisor listening at %s", self.app_sock_path)

    async def _reconcile_from_disk(self) -> None:
        """Re-spawn a broker for every integration persisted in the vault.

        Spawns concurrently so a slow upstream login on one integration
        doesn't delay others. Per-integration failures are logged and
        skipped — a single broken integration shouldn't keep the
        supervisor (or its siblings) from coming up. Skipped integrations
        remain on disk; the user can re-add them through the normal flow.
        """
        manager = self._manager
        if manager is None:
            msg = "_reconcile_from_disk called before start()"
            raise RuntimeError(msg)
        integration_ids = list_integration_ids(self.vault_dir)
        if not integration_ids:
            return

        logger.info("reconciling %d integration(s) from vault", len(integration_ids))
        results = await asyncio.gather(
            *(manager.reconcile_existing(iid) for iid in integration_ids),
            return_exceptions=True,
        )
        for integration_id, result in zip(integration_ids, results, strict=True):
            if isinstance(result, ReconcileError):
                logger.warning("reconcile failed for %s: %s", integration_id, result)
            elif isinstance(result, BaseException):
                logger.exception(
                    "reconcile errored unexpectedly for %s",
                    integration_id, exc_info=result,
                )

    async def stop(self) -> None:
        """Shut down every broker, close the listener.

        Best-effort: the manager cancels watchers and SIGTERMs every broker
        (with SIGKILL fallback after a grace window). The app.sock listener
        closes last so callers that still have in-flight ``add`` / ``remove``
        calls get their responses before we tear down.
        """
        if self._manager is not None:
            await self._manager.stop_all()

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        logger.info("supervisor shut down")
