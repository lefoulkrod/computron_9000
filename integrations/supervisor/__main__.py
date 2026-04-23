"""``python -m integrations.supervisor`` entry point.

Reads the vault / socket locations from env, starts the :class:`Supervisor`,
and blocks until SIGTERM or SIGINT. Intended for manual testing and eventually
for the container entrypoint.

Required env::

    SUPERVISOR_VAULT_DIR=/path/to/vault        # .master-key + creds/ live here
    SUPERVISOR_APP_SOCK=/path/to/app.sock       # where the app server connects
    SUPERVISOR_SOCKETS_DIR=/path/to/sockets     # per-broker UDS sockets

Exit codes: 0 on clean shutdown, 1 on startup failure.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

from integrations._env import env_required
from integrations.supervisor._catalog import DEFAULT_CATALOG
from integrations.supervisor._lifecycle import Supervisor

logger = logging.getLogger("supervisor")


async def _run() -> int:
    vault_dir = Path(env_required("SUPERVISOR_VAULT_DIR"))
    app_sock_path = Path(env_required("SUPERVISOR_APP_SOCK"))
    sockets_dir = Path(env_required("SUPERVISOR_SOCKETS_DIR"))

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
