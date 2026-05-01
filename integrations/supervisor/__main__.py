"""``python -m integrations.supervisor`` entry point.

Starts the :class:`Supervisor` and blocks until SIGTERM or SIGINT. Paths default
to the container-native layout and can be overridden via env vars for local
development or alternative deployments.

Env overrides (all optional)::

    SUPERVISOR_VAULT_DIR        default /var/lib/computron/vault     (persistent)
    SUPERVISOR_APP_SOCK         default /run/cvault/app.sock         (tmpfs)
    SUPERVISOR_SOCKETS_DIR      default /run/cvault                  (tmpfs)
    SUPERVISOR_DOWNLOADS_DIR    default /home/computron/downloads    (downloads)

The downloads dir is the shared "downloads" host-path role — agent-initiated
retrievals (browser saves, email attachments) land here. It's threaded into
the supervisor as a :class:`HostPath` registry entry, not a hardcoded
parameter, so future broker kinds that want their own shared dirs can opt
in via the catalog without touching this entry point.

Exit codes: 0 on clean shutdown, 1 on startup failure.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from integrations._perms import PROCESS_UMASK, disable_core_dumps
from integrations.supervisor._catalog import DEFAULT_CATALOG
from integrations.supervisor._lifecycle import Supervisor
from integrations.supervisor.types import HostPath

# Owner-only by default for everything this process creates. Specific call
# sites still set explicit modes (e.g. 0o660 sockets), but anything created
# without an explicit mode lands at 0o700 / 0o600 — see integrations/_perms.py.
os.umask(PROCESS_UMASK)

# No core dumps — the supervisor holds the master key in memory while
# decrypt operations are in flight, and the rlimit is inherited by every
# broker it spawns. A kernel-generated core would write that memory to
# disk where the computron UID could read it.
disable_core_dumps()

logger = logging.getLogger("supervisor")

_DEFAULT_VAULT_DIR = "/var/lib/computron/vault"
_DEFAULT_APP_SOCK = "/run/cvault/app.sock"
_DEFAULT_SOCKETS_DIR = "/run/cvault"
_DEFAULT_DOWNLOADS_DIR = "/home/computron/downloads"


def _build_host_paths() -> dict[str, HostPath]:
    """Construct the production host-path registry from defaults + env overrides."""
    downloads_dir = Path(
        os.environ.get("SUPERVISOR_DOWNLOADS_DIR", _DEFAULT_DOWNLOADS_DIR),
    )
    return {
        "downloads": HostPath(
            path=downloads_dir,
            description="agent-retrieved files (browser saves, email attachments)",
            owner="computron",
            group="broker",
            mode=0o3770,
        ),
    }


async def _run() -> int:
    vault_dir = Path(os.environ.get("SUPERVISOR_VAULT_DIR", _DEFAULT_VAULT_DIR))
    app_sock_path = Path(os.environ.get("SUPERVISOR_APP_SOCK", _DEFAULT_APP_SOCK))
    sockets_dir = Path(os.environ.get("SUPERVISOR_SOCKETS_DIR", _DEFAULT_SOCKETS_DIR))

    sup = Supervisor(
        vault_dir=vault_dir,
        app_sock_path=app_sock_path,
        sockets_dir=sockets_dir,
        host_paths=_build_host_paths(),
        catalog=DEFAULT_CATALOG,
    )
    await sup.start()

    # Block until SIGTERM / SIGINT; asyncio's signal handler just sets an event.
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    try:
        await stop.wait()
    finally:
        await sup.stop()
    return 0


def main() -> None:
    """Configure logging, run the async body, exit with its return code."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="[%(name)s] %(asctime)s %(levelname)s %(message)s",
    )
    try:
        code = asyncio.run(_run())
    except KeyboardInterrupt:
        code = 0
    sys.exit(code)


if __name__ == "__main__":
    main()
