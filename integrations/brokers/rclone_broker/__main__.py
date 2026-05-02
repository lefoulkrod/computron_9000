"""Rclone broker entry point: ``python -m integrations.brokers.rclone_broker``.

The supervisor spawns this with credentials and policy in the environment,
reads ``READY\n`` from stdout as the signal the broker is serving, and later
sends SIGTERM to shut it down.

Exit codes:
- 0: clean shutdown.
- 77: rclone authentication was rejected. The supervisor flips the
  integration to ``auth_failed`` and does not restart.
- 1: anything else (env-parse failure, network unreachable, internal error).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

from integrations._env import env_required, parse_bool
from integrations._perms import PROCESS_UMASK
from integrations._rpc import serve_rpc
from integrations.brokers._common._exit_codes import AUTH_FAIL, CLEAN_SHUTDOWN, GENERIC_ERROR
from integrations.brokers._common._ready import print_ready
from integrations.brokers.rclone_broker._verbs import VerbDispatcher

logger = logging.getLogger("rclone_broker")

os.umask(PROCESS_UMASK)


async def _run() -> int:
    integration_id = env_required("INTEGRATION_ID")
    socket_path = Path(env_required("BROKER_SOCKET"))
    write_allowed = parse_bool(env_required("WRITE_ALLOWED"))
    downloads_dir = Path(env_required("DOWNLOADS_DIR"))

    log = logging.getLogger(f"rclone_broker[{integration_id}]")

    # Verify rclone is available
    try:
        proc = await asyncio.create_subprocess_exec(
            "rclone", "version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        if proc.returncode != 0:
            log.error("rclone binary not functional")
            return GENERIC_ERROR
    except FileNotFoundError:
        log.error("rclone binary not found")
        return GENERIC_ERROR

    # Test authentication by running rclone about
    try:
        proc = await asyncio.create_subprocess_exec(
            "rclone", "about", "default:",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            stderr_str = stderr.decode("utf-8", errors="replace")
            stdout_str = stdout.decode("utf-8", errors="replace")
            combined = stderr_str + stdout_str
            # Check for auth-related errors
            auth_indicators = ["unauthorized", "authentication", "auth", "403", "401", "permission denied", "access denied"]
            if any(ind in combined.lower() for ind in auth_indicators):
                log.error("rclone auth rejected: %s", combined.strip())
                return AUTH_FAIL
            log.error("rclone about failed: %s", combined.strip())
            return GENERIC_ERROR
    except FileNotFoundError:
        log.error("rclone binary not found")
        return GENERIC_ERROR

    dispatcher = VerbDispatcher(
        write_allowed=write_allowed,
        downloads_dir=downloads_dir,
    )

    async def handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        return await dispatcher.dispatch(verb, args)

    server = await serve_rpc(socket_path, handler)
    log.info("listening on %s (write_allowed=%s)", socket_path, write_allowed)

    print_ready()

    async with server:
        try:
            await server.serve_forever()
        except asyncio.CancelledError:
            log.info("shutting down")
    return CLEAN_SHUTDOWN


def main() -> None:
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
