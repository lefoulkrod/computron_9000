"""Google Workspace broker entry point: ``python -m integrations.brokers.google_workspace_broker``.

The supervisor spawns this with OAuth tokens in the environment, reads
``READY\\n`` from stdout once the broker has verified the tokens by
issuing a fresh access-token refresh, and later sends SIGTERM to shut
it down.

Exit codes (see :mod:`integrations.brokers._common._exit_codes`):

- 0: clean shutdown.
- 77: refresh token rejected by Google. The supervisor flips state to
  ``auth_failed`` and stops respawning; recovery is delete + re-add.
- 1: anything else (env-parse failure, network unreachable, internal error).
  Supervisor backoff applies.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials

from integrations._env import env_required, parse_bool
from integrations._perms import PROCESS_UMASK, disable_core_dumps
from integrations._rpc import serve_rpc
from integrations.brokers._common._exit_codes import AUTH_FAIL, CLEAN_SHUTDOWN, GENERIC_ERROR
from integrations.brokers._common._ready import print_ready
from integrations.brokers.google_workspace_broker._verbs import VerbDispatcher

logger = logging.getLogger("google_workspace_broker")

# Owner-only by default for everything this process creates. Specific call
# sites still set explicit modes (e.g. 0o660 sockets) — see integrations/_perms.py.
os.umask(PROCESS_UMASK)

# No core dumps — the broker holds OAuth tokens in memory, and a kernel-
# generated core file would write that memory to disk.
disable_core_dumps()


# All OAuth env-var names the supervisor injects from the encrypted
# token bundle. Listed once here so we wipe each one from os.environ
# after capturing into the TokenBundle.
_OAUTH_ENV_VARS = (
    "OAUTH_CLIENT_ID",
    "OAUTH_CLIENT_SECRET",
    "OAUTH_ACCESS_TOKEN",
    "OAUTH_REFRESH_TOKEN",
    "OAUTH_TOKEN_URI",
    "OAUTH_SCOPES",
    "OAUTH_EXPIRES_AT",
)


async def _run() -> int:
    integration_id = env_required("INTEGRATION_ID")
    socket_path = Path(env_required("BROKER_SOCKET"))
    write_allowed = parse_bool(env_required("WRITE_ALLOWED"))

    expires_raw = int(env_required("OAUTH_EXPIRES_AT"))
    creds = Credentials(
        token=env_required("OAUTH_ACCESS_TOKEN"),
        refresh_token=env_required("OAUTH_REFRESH_TOKEN"),
        token_uri=env_required("OAUTH_TOKEN_URI"),
        client_id=env_required("OAUTH_CLIENT_ID"),
        client_secret=env_required("OAUTH_CLIENT_SECRET"),
        scopes=env_required("OAUTH_SCOPES").split(),
        # Credentials.expiry is a *naive* UTC datetime. The blob carries
        # a unix-epoch int because that's what the env-injection wire
        # format has used since v1; an int of 0 means "no known expiry"
        # and the lib treats None the same way.
        expiry=(
            datetime.fromtimestamp(expires_raw, tz=UTC).replace(tzinfo=None)
            if expires_raw else None
        ),
    )

    # Wipe OAuth fields from the process environ once captured into the
    # credentials. Same hygiene as email_broker's EMAIL_PASS pop — narrows
    # in-process exposure (debuggers, traceback locals, crash captures).
    # Doesn't change /proc/<pid>/environ since glibc doesn't update it on
    # os.environ writes, but the agent UID can't read that path anyway.
    for var in _OAUTH_ENV_VARS:
        os.environ.pop(var, None)

    # Per-integration logger — lets a reader of ``docker logs`` pick one
    # broker's output out of several running in the same container.
    log = logging.getLogger(f"google_workspace_broker[{integration_id}]")

    try:
        # Force a refresh as a liveness check: catches the case where
        # Google revoked our refresh token between the OAuth handshake
        # and broker spawn. Without this we'd READY-then-fail on the
        # first agent verb call.
        await asyncio.to_thread(creds.refresh, Request())
    except RefreshError as exc:
        log.error("OAuth refresh rejected: %s", exc)
        return AUTH_FAIL
    except OSError as exc:
        # Network-level failure (DNS, no route, connection refused).
        # Different supervisor response from auth failure — we come back
        # up on backoff.
        log.error("OAuth refresh network error: %s", exc)
        return GENERIC_ERROR

    session = AuthorizedSession(creds)
    dispatcher = VerbDispatcher(session=session, write_allowed=write_allowed)

    async def handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        return await dispatcher.dispatch(verb, args)

    server = await serve_rpc(socket_path, handler)
    log.info(
        "listening on %s (write_allowed=%s, scopes=%s)",
        socket_path, write_allowed, " ".join(creds.scopes or ()),
    )

    # READY sentinel: the supervisor watches stdout for this exact line and
    # flips the integration from ``pending`` to ``running`` on seeing it.
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
