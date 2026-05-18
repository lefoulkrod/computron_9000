"""Rclone broker entry point: ``python -m integrations.brokers.rclone_broker``.

The supervisor spawns this with the rclone remote config and policy in the
environment, reads ``READY\\n`` from stdout as the signal the broker is
serving, and later sends SIGTERM to shut it down.

Exit codes the supervisor reacts to (see ``integrations.brokers._common._exit_codes``):

- 0: clean shutdown.
- 77: rclone couldn't authenticate against the configured remote. The
  supervisor flips the integration to ``auth_failed`` and stops respawning.
- 1: anything else (rclone binary missing, network unreachable, env problem).

rclone reads its remote definition entirely from ``RCLONE_CONFIG_DEFAULT_*``
env vars — there is no config file. The broker probes the remote once with
``rclone about default:`` before serving so a bad credential surfaces as a
clean exit 77 rather than a per-verb failure later.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

from integrations._env import env_required
from integrations._perms import PROCESS_UMASK, disable_core_dumps
from integrations._rpc import serve_rpc
from integrations.brokers._common._exit_codes import AUTH_FAIL, CLEAN_SHUTDOWN, GENERIC_ERROR
from integrations.brokers._common._ready import print_ready
from integrations.brokers.rclone_broker._verbs import VerbDispatcher
from integrations.permissions import permissions_from_env

logger = logging.getLogger("rclone_broker")

os.umask(PROCESS_UMASK)

# No core dumps — the rclone remote config (in this process's environ) contains
# the user's Apple ID password and trust token.
disable_core_dumps()

# Substrings that, when rclone fails, point at a credential problem rather than
# a transient network one. Best-effort: rclone doesn't give a stable auth exit code.
_AUTH_FAILURE_HINTS = (
    "unauthorized", "authentication", "401", "403",
    "permission denied", "access denied", "invalid credentials",
    "login failed", "2fa", "two-factor",
)


async def _probe_rclone() -> int | None:
    """Verify the rclone binary works and the configured remote authenticates.

    Returns ``None`` on success, or an exit code to bail with.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "rclone", "about", "default:", "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        logger.error("rclone binary not found on PATH")
        return GENERIC_ERROR
    stdout, stderr = await proc.communicate()
    if proc.returncode == 0:
        return None
    combined = (stderr.decode("utf-8", errors="replace") + stdout.decode("utf-8", errors="replace")).strip()
    if any(hint in combined.lower() for hint in _AUTH_FAILURE_HINTS):
        logger.error("rclone authentication rejected: %s", combined)
        return AUTH_FAIL
    logger.error("rclone probe failed: %s", combined)
    return GENERIC_ERROR


async def _run() -> int:
    integration_id = env_required("INTEGRATION_ID")
    socket_path = Path(env_required("BROKER_SOCKET"))
    permissions = permissions_from_env(env_required("PERMISSIONS"))
    downloads_dir = Path(env_required("DOWNLOADS_DIR"))

    log = logging.getLogger(f"rclone_broker[{integration_id}]")

    bail = await _probe_rclone()
    if bail is not None:
        return bail

    dispatcher = VerbDispatcher(permissions=permissions, downloads_dir=downloads_dir)

    async def handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        return await dispatcher.dispatch(verb, args)

    server = await serve_rpc(socket_path, handler)
    log.info("listening on %s (permissions=%s)", socket_path, permissions)

    print_ready()

    async with server:
        try:
            await server.serve_forever()
        except asyncio.CancelledError:
            log.info("shutting down")
    return CLEAN_SHUTDOWN


def main() -> None:
    """Console entry point — configure logging, run the async body, exit with its code."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="[%(name)s] %(asctime)s %(levelname)s %(message)s",
    )
    try:
        code = asyncio.run(_run())
    except KeyboardInterrupt:
        code = CLEAN_SHUTDOWN
    sys.exit(code)


if __name__ == "__main__":
    main()
