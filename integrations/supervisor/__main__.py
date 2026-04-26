"""``python -m integrations.supervisor`` entry point.

Starts the :class:`Supervisor` and blocks until SIGTERM or SIGINT. Paths default
to the container-native layout and can be overridden via env vars for local
development or alternative deployments.

Env overrides (all optional)::

    SUPERVISOR_VAULT_DIR     default /var/lib/computron/vault   (persistent)
    SUPERVISOR_APP_SOCK      default /run/cvault/app.sock       (tmpfs)
    SUPERVISOR_SOCKETS_DIR   default /run/cvault                (tmpfs)

Exit codes: 0 on clean shutdown, 1 on startup failure.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from integrations._perms import PROCESS_UMASK
from integrations.supervisor._catalog import DEFAULT_CATALOG
from integrations.supervisor._lifecycle import Supervisor

# Owner-only by default for everything this process creates. Specific call
# sites still set explicit modes (e.g. 0o660 sockets), but anything created
# without an explicit mode lands at 0o700 / 0o600 — see integrations/_perms.py.
os.umask(PROCESS_UMASK)

logger = logging.getLogger("supervisor")

_DEFAULT_VAULT_DIR = "/var/lib/computron/vault"
_DEFAULT_APP_SOCK = "/run/cvault/app.sock"
_DEFAULT_SOCKETS_DIR = "/run/cvault"


async def _run() -> int:
    vault_dir = Path(os.environ.get("SUPERVISOR_VAULT_DIR", _DEFAULT_VAULT_DIR))
    app_sock_path = Path(os.environ.get("SUPERVISOR_APP_SOCK", _DEFAULT_APP_SOCK))
    sockets_dir = Path(os.environ.get("SUPERVISOR_SOCKETS_DIR", _DEFAULT_SOCKETS_DIR))

    sup = Supervisor(
        vault_dir=vault_dir,
        app_sock_path=app_sock_path,
        sockets_dir=sockets_dir,
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
