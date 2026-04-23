"""Spawn the broker subprocess for one integration; wait for READY sentinel.

Called by the supervisor's ``add`` path. Produces a :class:`BrokerHandle` the
registry stores until the integration is removed. If the broker exits before
printing ``READY\\n``, we surface the exit code so the caller can distinguish
auth-fail (``77``) from a generic failure (``1``) and respond accordingly.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from integrations.supervisor._catalog import CatalogEntry

logger = logging.getLogger(__name__)

_READY_TIMEOUT_SECONDS = 30.0


class BrokerSpawnError(Exception):
    """Broker subprocess failed to reach READY — early exit, timeout, or env problem.

    ``exit_code`` is populated when we observed a definite exit code (so the caller
    can distinguish ``77`` / auth failure from ``1`` / network failure). It's
    ``None`` when the broker hit the READY-timeout and we had to SIGKILL it.
    """

    def __init__(self, message: str, *, exit_code: int | None = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass
class BrokerHandle:
    """The running broker subprocess for one integration."""

    integration_id: str
    socket_path: Path
    proc: asyncio.subprocess.Process


async def spawn_broker(
    *,
    entry: CatalogEntry,
    integration_id: str,
    secret_bundle: dict,
    write_allowed: bool,
    sockets_dir: Path,
) -> BrokerHandle:
    """Spawn the broker for ``integration_id`` from its catalog entry.

    Combines the entry's static env, the credential-to-env mapping, and the
    per-spawn ``INTEGRATION_ID`` / ``BROKER_SOCKET`` / ``WRITE_ALLOWED`` vars.
    Awaits ``READY\\n`` on the subprocess's stdout before returning.
    """
    sockets_dir.mkdir(parents=True, exist_ok=True)
    socket_path = sockets_dir / f"{integration_id}.sock"

    # Start from the supervisor's own env so the child inherits PATH, VIRTUAL_ENV,
    # and whatever else Python needs to resolve. Our explicit overrides win on
    # conflict. When we harden the container, swap to a curated allow-list.
    env: dict[str, str] = dict(os.environ)
    env.update(entry.static_env)
    for blob_key, env_name in entry.env_injection.items():
        if blob_key not in secret_bundle:
            msg = f"env_injection references missing auth field: {blob_key!r}"
            raise BrokerSpawnError(msg)
        env[env_name] = secret_bundle[blob_key]
    env["INTEGRATION_ID"] = integration_id
    env["BROKER_SOCKET"] = str(socket_path)
    env["WRITE_ALLOWED"] = "true" if write_allowed else "false"

    logger.info("spawning broker for %s at %s", integration_id, socket_path)

    proc = await asyncio.create_subprocess_exec(
        *entry.command,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.DEVNULL,
    )

    try:
        await asyncio.wait_for(_wait_for_ready(proc), timeout=_READY_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        # Broker hung during its handshake — SIGKILL + reap so we don't orphan.
        proc.kill()
        await proc.wait()
        msg = f"broker did not print READY within {_READY_TIMEOUT_SECONDS}s"
        raise BrokerSpawnError(msg, exit_code=None) from exc

    return BrokerHandle(
        integration_id=integration_id,
        socket_path=socket_path,
        proc=proc,
    )


async def _wait_for_ready(proc: asyncio.subprocess.Process) -> None:
    """Read broker stdout until the ``READY`` line — or raise if it exits first."""
    # ``proc.stdout`` is typed ``StreamReader | None`` because asyncio only wires
    # it when the subprocess was spawned with ``stdout=PIPE``. We always are
    # above, but the type checker can't see that. Capture to a local so the
    # loop below sees a plain ``StreamReader`` without a runtime assert.
    stdout = proc.stdout
    if stdout is None:
        msg = "broker subprocess was spawned without a stdout pipe"
        raise BrokerSpawnError(msg)
    while True:
        line = await stdout.readline()
        if not line:
            # EOF on stdout: broker exited without emitting READY. wait() gives us
            # the definite exit code.
            code = await proc.wait()
            msg = f"broker exited with code {code} before READY"
            raise BrokerSpawnError(msg, exit_code=code)
        text = line.decode("utf-8", errors="replace").rstrip("\r\n")
        if text == "READY":
            return
        # Any pre-READY chatter (shouldn't happen under our broker's contract but
        # costs little to log) ends up in the supervisor's own logs.
        logger.info("broker stdout pre-READY: %s", text)
