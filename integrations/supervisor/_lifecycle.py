"""Top-level supervisor lifecycle: master key, registry, app.sock listener.

The :class:`Supervisor` class is what tests instantiate and what ``__main__``
will eventually wire up. It doesn't run a loop itself — the caller awaits
``start()``, does its work (or blocks on ``serve_forever`` in production), then
awaits ``stop()``.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from integrations._rpc import serve_rpc
from integrations.supervisor._app_sock import AppSockHandler
from integrations.supervisor._catalog import CatalogEntry
from integrations.supervisor._crypto import load_or_init_master_key
from integrations.supervisor._registry import Registry

logger = logging.getLogger(__name__)

_SHUTDOWN_GRACE_SECONDS = 5.0


class Supervisor:
    """Owns the vault, the registry, and the ``app.sock`` listener.

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
        catalog: dict[str, CatalogEntry],
    ) -> None:
        self.vault_dir = vault_dir
        self.app_sock_path = app_sock_path
        self.sockets_dir = sockets_dir
        self.catalog = catalog

        self._master_key: bytes | None = None
        self._registry: Registry | None = None
        self._handler: AppSockHandler | None = None
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        """Initialize vault dir, master key, registry; bind ``app.sock``."""
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.sockets_dir.mkdir(parents=True, exist_ok=True)

        self._master_key = load_or_init_master_key(self.vault_dir)
        self._registry = Registry()
        self._handler = AppSockHandler(
            vault_dir=self.vault_dir,
            sockets_dir=self.sockets_dir,
            master_key=self._master_key,
            catalog=self.catalog,
            registry=self._registry,
        )
        self._server = await serve_rpc(self.app_sock_path, self._handler.handle)
        logger.info("supervisor listening at %s", self.app_sock_path)

    async def stop(self) -> None:
        """Shut down every broker, close the listener.

        Best-effort: we SIGTERM every broker and wait up to a small grace
        window each; anything still alive gets SIGKILLed. The app.sock listener
        closes last so callers that still have in-flight ``add`` / ``remove``
        calls get their responses before we tear down.
        """
        if self._registry is not None:
            for record in self._registry.list():
                if record.broker.proc.returncode is None:
                    record.broker.proc.terminate()
            for record in self._registry.list():
                try:
                    await asyncio.wait_for(
                        record.broker.proc.wait(), timeout=_SHUTDOWN_GRACE_SECONDS,
                    )
                except TimeoutError:
                    record.broker.proc.kill()
                    await record.broker.proc.wait()

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        logger.info("supervisor shut down")
