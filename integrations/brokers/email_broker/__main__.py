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

Each upstream — IMAP, SMTP, CalDAV — is brought up in turn. SMTP and CalDAV
are optional (a catalog entry without ``SMTP_HOST`` or ``CALDAV_URL`` skips
the corresponding bring-up). An auth rejection from any of them maps to exit
77 so the supervisor flips state to ``auth_failed`` and stops respawning.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

from integrations._env import env_required, parse_bool
from integrations._perms import PROCESS_UMASK, disable_core_dumps
from integrations._rpc import serve_rpc
from integrations.brokers._common._exit_codes import AUTH_FAIL, CLEAN_SHUTDOWN, GENERIC_ERROR
from integrations.brokers._common._ready import print_ready
from integrations.brokers.email_broker._caldav_client import CalDavAuthError, CalDavClient
from integrations.brokers.email_broker._imap_client import ImapAuthError, ImapClient
from integrations.brokers.email_broker._smtp_client import SmtpAuthError, SmtpClient
from integrations.brokers.email_broker._verbs import VerbDispatcher

logger = logging.getLogger("email_broker")

# Owner-only by default for everything this process creates. Specific call
# sites still set explicit modes (e.g. 0o660 sockets) — see integrations/_perms.py.
os.umask(PROCESS_UMASK)

# No core dumps — the broker holds the decrypted credential in memory,
# and a kernel-generated core file would write that memory to disk.
disable_core_dumps()


async def _run() -> int:
    integration_id = env_required("INTEGRATION_ID")
    socket_path = Path(env_required("BROKER_SOCKET"))
    imap_host = env_required("IMAP_HOST")
    imap_port = int(env_required("IMAP_PORT"))
    user = env_required("EMAIL_USER")
    password = env_required("EMAIL_PASS")
    write_allowed = parse_bool(env_required("WRITE_ALLOWED"))
    attachments_dir = Path(env_required("ATTACHMENTS_DIR"))

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

    # SMTP is optional — present only when the catalog entry provides
    # ``SMTP_HOST`` / ``SMTP_PORT``. Brokers without it can still serve all
    # read verbs and IMAP-side writes (move, future flag); send_message
    # responds with "not implemented" until a host is configured.
    smtp_client: SmtpClient | None = None
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port_raw = os.environ.get("SMTP_PORT")
    if smtp_host and smtp_port_raw:
        smtp_client = SmtpClient(
            host=smtp_host,
            port=int(smtp_port_raw),
            user=user,
            password=password,
            # Production iCloud / Gmail use port 587 STARTTLS. The fake fixture
            # speaks plaintext SMTP and sets ``SMTP_STARTTLS=false`` to exercise
            # the broker without a TLS terminator.
            starttls=parse_bool(os.environ.get("SMTP_STARTTLS", "true")),
        )
        try:
            await smtp_client.connect()
        except SmtpAuthError as exc:
            log.error("SMTP AUTH rejected: %s", exc)
            return AUTH_FAIL
        except OSError as exc:
            log.error("SMTP connect failed: %s", exc)
            return GENERIC_ERROR

    # CalDAV is optional — the catalog entry sets ``CALDAV_URL`` only for
    # providers that support it. Brokers spawned for an email-only catalog
    # entry (or a future MCP-only one) skip CalDAV bring-up entirely.
    caldav_client: CalDavClient | None = None
    caldav_url = os.environ.get("CALDAV_URL")
    if caldav_url:
        caldav_client = CalDavClient(url=caldav_url, username=user, password=password)
        try:
            await caldav_client.connect()
        except CalDavAuthError as exc:
            log.error("CalDAV auth rejected: %s", exc)
            return AUTH_FAIL
        except OSError as exc:
            log.error("CalDAV connect failed: %s", exc)
            return GENERIC_ERROR

    dispatcher = VerbDispatcher(
        imap=imap,
        smtp=smtp_client,
        caldav=caldav_client,
        write_allowed=write_allowed,
        attachments_dir=attachments_dir,
    )

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
