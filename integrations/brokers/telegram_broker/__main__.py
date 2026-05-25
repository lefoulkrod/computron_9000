"""Telegram broker entry point: ``python -m integrations.brokers.telegram_broker``.

The supervisor spawns this with credentials and policy in the environment,
reads ``READY\\n`` from stdout as the signal the broker is serving, and later
sends SIGTERM to shut it down.

Exit codes:

- 0: clean shutdown.
- 77: the bot token was rejected by Telegram. The supervisor flips the
  integration to ``auth_failed`` and does not restart.
- 1: anything else (env-parse failure, network unreachable, allowlist empty,
  internal error). The supervisor transitions to ``error`` and restarts on
  backoff.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramUnauthorizedError

from integrations._env import env_required
from integrations._perms import PROCESS_UMASK, disable_core_dumps
from integrations._rpc import serve_rpc
from integrations.brokers._common._exit_codes import AUTH_FAIL, CLEAN_SHUTDOWN, GENERIC_ERROR
from integrations.brokers._common._ready import print_ready
from integrations.brokers.telegram_broker._updates import UpdatePump
from integrations.brokers.telegram_broker._verbs import VerbDispatcher
from integrations.permissions import permissions_from_env

logger = logging.getLogger("telegram_broker")

# Owner-only by default for everything this process creates. Specific call
# sites still set explicit modes (e.g. 0o660 sockets) — see integrations/_perms.py.
os.umask(PROCESS_UMASK)

# No core dumps — the broker holds the bot token in memory, and a
# kernel-generated core file would write it to disk.
disable_core_dumps()


def _parse_allowed_user_ids(raw: str) -> frozenset[int]:
    """Parse a comma-separated user ID list. Bad entries logged and skipped."""
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            logger.warning("TELEGRAM_ALLOWED_USER_IDS entry is not an integer: %r", part)
    return frozenset(out)


async def _run() -> int:
    integration_id = env_required("INTEGRATION_ID")
    socket_path = Path(env_required("BROKER_SOCKET"))
    token = env_required("TELEGRAM_BOT_TOKEN")
    permissions = permissions_from_env(env_required("PERMISSIONS"))
    allowed = _parse_allowed_user_ids(env_required("TELEGRAM_ALLOWED_USER_IDS"))
    downloads_dir = Path(env_required("DOWNLOADS_DIR"))

    # Wipe the token from the process environ once captured. Best-effort
    # hygiene: narrows in-process exposure (debuggers, traceback locals,
    # crash-reporter captures). The kernel's /proc/<pid>/environ snapshot is
    # set at exec time and won't update; that file is mode 0400 and the
    # agent runs as a different UID, so it's not a concern regardless.
    os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    os.environ.pop("TELEGRAM_ALLOWED_USER_IDS", None)

    log = logging.getLogger(f"telegram_broker[{integration_id}]")

    if not allowed:
        # Fail closed at boot. A Telegram bot has no Telegram-side ACL, so an
        # empty allowlist would let anyone who discovers the bot username drive
        # the agent. Refuse to start rather than silently accept everyone.
        log.error("TELEGRAM_ALLOWED_USER_IDS is empty; refusing to start")
        return GENERIC_ERROR

    bot = Bot(token=token)

    # Identity probe: detects an invalid/revoked token before we start polling.
    try:
        me = await bot.get_me()
    except TelegramUnauthorizedError as exc:
        log.error("Telegram rejected the bot token: %s", exc)
        await bot.session.close()
        return AUTH_FAIL
    except OSError as exc:
        # Network-level failure — supervisor retries on backoff.
        log.error("could not reach Telegram: %s", exc)
        await bot.session.close()
        return GENERIC_ERROR

    log.info(
        "authenticated as @%s (id=%d) allowed_user_ids=%s",
        me.username, me.id, sorted(allowed),
    )

    pump = UpdatePump(
        bot, allowed,
        integration_id=integration_id,
        downloads_dir=downloads_dir,
    )
    pump_task = asyncio.create_task(pump.run(), name="telegram-update-pump")

    dispatcher = VerbDispatcher(bot, pump, permissions=permissions)

    async def handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        return await dispatcher.dispatch(verb, args)

    server = await serve_rpc(socket_path, handler)
    log.info("listening on %s (permissions=%s)", socket_path, permissions)

    # READY sentinel: the supervisor watches stdout for this exact line and
    # flips the integration from ``pending`` to ``active`` on seeing it.
    print_ready()

    async with server:
        try:
            done, _ = await asyncio.wait(
                [pump_task, asyncio.create_task(server.serve_forever())],
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            log.info("shutting down")
            done = set()

    # If the pump exited cleanly with auth_failed=True, that's the only path
    # that should map to a 77 exit; cancellation or server-finished is clean.
    if pump.auth_failed:
        await bot.session.close()
        return AUTH_FAIL

    pump_task.cancel()
    try:
        await pump_task
    except (asyncio.CancelledError, Exception):
        pass

    await bot.session.close()
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
