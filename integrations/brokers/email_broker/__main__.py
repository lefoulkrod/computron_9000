"""Email broker entry point: ``python -m integrations.brokers.email_broker``.

The supervisor spawns this with credentials and policy in the environment,
reads ``READY\\n`` from stdout as the signal the broker is serving, and later
sends SIGTERM to shut it down.

Exit codes the supervisor reacts to (see ``integrations.brokers._common._exit_codes``):

- 0: clean shutdown.
- 77: IMAP LOGIN was rejected by the server. The supervisor flips the
  integration to ``auth_failed`` and does not restart.
- 1: anything else (env-parse failure, network unreachable, internal error).
  The supervisor transitions to ``error`` and restarts on backoff.

Walking-skeleton scope: only the IMAP read-side is wired. SMTP and write verbs
are declared in the verb table but respond with ``BAD_REQUEST`` until we add
their handlers. This is deliberate — it lets us smoke-test the full plumbing
against a real IMAP server before the surface area grows.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

from integrations._env import env_required, parse_bool
from integrations.brokers._common._exit_codes import AUTH_FAIL, CLEAN_SHUTDOWN, GENERIC_ERROR
from integrations.brokers._common._ready import print_ready
from integrations._rpc import serve_rpc
from integrations.brokers.email_broker._imap_client import ImapAuthError, ImapClient
from integrations.brokers.email_broker._verbs import VerbDispatcher

logger = logging.getLogger("email_broker")


async def _run() -> int:
    integration_id = env_required("INTEGRATION_ID")
    socket_path = Path(env_required("BROKER_SOCKET"))
    imap_host = env_required("IMAP_HOST")
    imap_port = int(env_required("IMAP_PORT"))
    user = env_required("EMAIL_USER")
    password = env_required("EMAIL_PASS")
    write_allowed = parse_bool(env_required("WRITE_ALLOWED"))

    # Wipe the password from the process environ once we've captured it into
    # local state. Best-effort hygiene: narrows in-process exposure (debuggers,
    # traceback locals, crash-reporter captures). Does NOT change
    # /proc/<pid>/environ — that's set at exec time and glibc doesn't update
    # it when Python modifies os.environ. That file is mode 0400 and the agent
    # runs as a different UID, so it's not a concern regardless.
    os.environ.pop("EMAIL_PASS", None)

    # Per-integration logger — lets a reader of ``docker logs`` pick one
    # broker's output out of several running in the same container.
    log = logging.getLogger(f"email_broker[{integration_id}]")

    imap = ImapClient(
        host=imap_host,
        port=imap_port,
        user=user,
        password=password,
        # TLS default: production uses port 993 with implicit TLS. For a manual
        # test against a plaintext server (e.g. a local fake) set IMAP_TLS=false.
        use_tls=parse_bool(os.environ.get("IMAP_TLS", "true")),
    )

    try:
        await imap.connect()
    except ImapAuthError as exc:
        log.error("IMAP LOGIN rejected: %s", exc)
        return AUTH_FAIL
    except OSError as exc:
        # Network-level failure (connection refused, no route, DNS). Different
        # supervisor response from auth failure — we come back up on backoff.
        log.error("IMAP connect failed: %s", exc)
        return GENERIC_ERROR

    dispatcher = VerbDispatcher(imap=imap, smtp=None, write_allowed=write_allowed)

    async def handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        return await dispatcher.dispatch(verb, args)

    server = await serve_rpc(socket_path, handler)
    log.info(
        "listening on %s (write_allowed=%s, host=%s:%d)",
        socket_path, write_allowed, imap_host, imap_port,
    )

    # READY sentinel: the supervisor watches stdout for this exact line and
    # flips the integration from ``pending`` to ``active`` on seeing it.
    print_ready()

    async with server:
        try:
            await server.serve_forever()
        except asyncio.CancelledError:
            # Normal shutdown path: SIGTERM -> asyncio.run cancels the task.
            log.info("shutting down")
    return CLEAN_SHUTDOWN


def main() -> None:
    """Console entry point — configure logging, run the async body, exit with its return code."""
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
