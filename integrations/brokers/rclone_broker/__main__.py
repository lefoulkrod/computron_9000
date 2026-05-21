"""Rclone broker entry point: ``python -m integrations.brokers.rclone_broker``.

The broker spawns one long-lived ``rclone rcd`` per integration and talks to
it over a local UDS using rclone's JSON-RPC API. All credential state —
Apple ID, password, trust token, session-acquired PCS cookies — lives only
in process memory: env vars are wiped after capture, rcd is configured via
RC API (not via config file), and on clean shutdown the broker pushes any
mutated session state back to the supervisor for re-encryption in the
vault.

Exit codes the supervisor reacts to:

- 0: clean shutdown.
- 77: rcd reported an upstream credential rejection. The supervisor flips
  the integration to ``auth_failed`` and stops respawning.
- 1: anything else (rcd binary missing, env-parse failure, network
  unreachable, internal error).
"""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any

from integrations import supervisor_client
from integrations._env import env_required
from integrations._perms import PROCESS_UMASK, disable_core_dumps
from integrations._rpc import serve_rpc
from integrations.brokers._common._exit_codes import AUTH_FAIL, CLEAN_SHUTDOWN, GENERIC_ERROR
from integrations.brokers._common._ready import print_ready
from integrations.brokers.rclone_broker._rcd import RcdAuthError, RcdClient, RcdError
from integrations.brokers.rclone_broker._verbs import VerbDispatcher
from integrations.permissions import permissions_from_env

logger = logging.getLogger("rclone_broker")

os.umask(PROCESS_UMASK)

# No core dumps — broker memory holds plaintext Apple ID, password, trust
# token, and PCS cookies. rcd, spawned later, inherits RLIMIT_CORE.
disable_core_dumps()

_REMOTE_NAME = "default"

# Linux mlockall(2) flags. Used best-effort — fails without CAP_IPC_LOCK
# (default for unprivileged containers), in which case we just log and
# carry on. Encrypted swap on the host is the alternate mitigation.
_MCL_CURRENT = 1
_MCL_FUTURE = 2


def _try_mlockall() -> None:
    """Pin broker memory in RAM so plaintext secrets don't land in swap.

    Best-effort: requires CAP_IPC_LOCK or sufficient RLIMIT_MEMLOCK. If
    neither is granted, we log a warning and continue — encrypted swap on
    the host is the alternate mitigation.
    """
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        rc = libc.mlockall(_MCL_CURRENT | _MCL_FUTURE)
    except OSError as exc:
        logger.warning("mlockall not available: %s", exc)
        return
    if rc == 0:
        logger.info("mlockall succeeded — broker pages pinned in RAM")
    else:
        errno = ctypes.get_errno()
        logger.warning(
            "mlockall failed (errno=%d) — broker pages may land in swap "
            "if the host has unencrypted swap configured",
            errno,
        )


def _pop_env(name: str) -> str | None:
    """Read and remove an env var so it doesn't linger in ``/proc/<pid>/environ``."""
    value = os.environ.pop(name, None)
    return value if value else None


async def _obscure_password(plaintext: str) -> str:
    """Run ``rclone obscure`` to convert a plaintext password into rclone's at-rest form.

    rclone reads passwords in env-var config as obscured (its reversible
    encoding); plaintext triggers a "input too short when revealing
    password" error inside the backend.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "rclone", "obscure", plaintext,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("rclone binary not found on PATH") from exc
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        # Don't include the plaintext password — log only the stderr.
        err = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"rclone obscure failed: {err}")
    return stdout.decode("utf-8", errors="replace").strip()


def _build_rclone_env(
    *,
    obscured_password: str,
    apple_id: str,
    trust_token: str,
    cookies: str | None,
    client_id: str | None,
) -> dict[str, str]:
    """Assemble the ``RCLONE_CONFIG_DEFAULT_*`` env vars for the rcd subprocess.

    rclone's configmap merges env vars and file values into one Map; from the
    backend's view there's no observable difference. Env-var-only config
    keeps credentials out of any filesystem path — only ``/proc/<rcd>/environ``
    (mode 0400, broker-uid-only) ever holds them.

    ``cookies`` and ``client_id`` are only included when a previous run
    produced them — on first spawn rclone generates its own client_id and
    fills in cookies after PCS approval.
    """
    env = {
        "RCLONE_CONFIG_DEFAULT_TYPE": "iclouddrive",
        "RCLONE_CONFIG_DEFAULT_APPLE_ID": apple_id,
        "RCLONE_CONFIG_DEFAULT_PASSWORD": obscured_password,
        "RCLONE_CONFIG_DEFAULT_TRUST_TOKEN": trust_token,
    }
    if cookies:
        env["RCLONE_CONFIG_DEFAULT_COOKIES"] = cookies
    if client_id:
        env["RCLONE_CONFIG_DEFAULT_CLIENT_ID"] = client_id
    return env


async def _probe_remote(rcd: RcdClient) -> int | None:
    """Force rcd to actually connect to iCloud Drive so PCS approval fires now.

    iCloud Drive's backend doesn't implement the rclone ``about`` op cleanly,
    so we probe with ``operations/list`` on the root path. Returns ``None``
    on success or an exit code to bail with.
    """
    try:
        await rcd.call("operations/list", {"fs": f"{_REMOTE_NAME}:", "remote": ""})
    except RcdAuthError as exc:
        logger.error("iCloud auth rejected: %s", exc)
        return AUTH_FAIL
    except RcdError as exc:
        logger.error("rcd probe failed: %s", exc)
        return GENERIC_ERROR
    return None


async def _push_secret_patch(
    *, app_sock_path: Path, integration_id: str, patch: dict[str, str],
) -> None:
    """Send ``patch`` to the supervisor via ``update_secrets``.

    Best-effort: failures are logged but don't abort shutdown — the broker
    can still exit cleanly even if persistence fails. The next spawn will
    just re-acquire whatever wasn't saved.
    """
    if not patch:
        return
    try:
        await supervisor_client.call(
            "update_secrets",
            {"id": integration_id, "patch": patch},
            app_sock_path=app_sock_path,
        )
        logger.info("pushed %d updated secret key(s) to the supervisor", len(patch))
    except Exception as exc:  # noqa: BLE001 — broad on purpose during shutdown
        logger.warning("failed to push secret patch to supervisor: %s", exc)


async def _checkpoint(
    *,
    rcd: RcdClient,
    app_sock_path: Path,
    integration_id: str,
    initial_cookies: str,
    initial_client_id: str,
) -> None:
    """Capture rcd's current session state and push any deltas to the supervisor.

    rcd may have populated ``cookies`` after PCS approval and may have
    generated its own ``client_id`` if we didn't pass one in. Either way,
    config/dump returns whatever is in rcd's in-memory config right now.
    """
    try:
        remote = await rcd.dump_remote_params(_REMOTE_NAME)
    except RcdError as exc:
        logger.warning("config/dump failed during checkpoint: %s", exc)
        return
    patch: dict[str, str] = {}
    current_cookies = str(remote.get("cookies") or "")
    if current_cookies and current_cookies != initial_cookies:
        patch["rclone_cookies"] = current_cookies
    current_client_id = str(remote.get("client_id") or "")
    if current_client_id and current_client_id != initial_client_id:
        patch["client_id"] = current_client_id
    await _push_secret_patch(
        app_sock_path=app_sock_path, integration_id=integration_id, patch=patch,
    )


async def _run() -> int:
    integration_id = env_required("INTEGRATION_ID")
    broker_socket = Path(env_required("BROKER_SOCKET"))
    permissions = permissions_from_env(env_required("PERMISSIONS"))
    downloads_dir = Path(env_required("DOWNLOADS_DIR"))
    app_sock_path = broker_socket.parent / "app.sock"

    apple_id = env_required("ICLOUD_APPLE_ID")
    password = _pop_env("ICLOUD_APPLE_PASSWORD")
    trust_token = _pop_env("ICLOUD_TRUST_TOKEN")
    cookies = _pop_env("ICLOUD_RCLONE_COOKIES") or ""
    initial_client_id = _pop_env("ICLOUD_RCLONE_CLIENT_ID")
    # Pull these into local state and immediately drop them from the environ
    # so /proc/<pid>/environ never has them — defense in depth on top of the
    # mode-0400 owner-only protection.
    os.environ.pop("ICLOUD_APPLE_ID", None)

    if not password or not trust_token:
        logger.error("ICLOUD_APPLE_PASSWORD and ICLOUD_TRUST_TOKEN are required")
        return GENERIC_ERROR

    log = logging.getLogger(f"rclone_broker[{integration_id}]")

    _try_mlockall()

    try:
        obscured = await _obscure_password(password)
    except RuntimeError as exc:
        log.error("%s", exc)
        return GENERIC_ERROR

    rclone_env = _build_rclone_env(
        obscured_password=obscured,
        apple_id=apple_id,
        trust_token=trust_token,
        cookies=cookies,
        client_id=initial_client_id,
    )

    rcd = RcdClient(
        integration_id=integration_id,
        socket_path=broker_socket.parent / f"{integration_id}.rclone.sock",
    )

    try:
        await rcd.start(remote_name=_REMOTE_NAME, rclone_env=rclone_env)
    except RcdAuthError as exc:
        log.error("rcd rejected the credentials: %s", exc)
        return AUTH_FAIL
    except RcdError as exc:
        log.error("rcd failed to start: %s", exc)
        return GENERIC_ERROR
    # rcd holds the credentials in its own environ now. Drop our local
    # references — the broker process doesn't need them past this point.
    password = ""
    obscured = ""
    trust_token = ""
    rclone_env = {}

    # Force the iCloud connection so PCS approval (if needed for ADP) happens
    # before we print READY — the wizard's "verifying" spinner waits on us.
    bail = await _probe_remote(rcd)
    if bail is not None:
        await rcd.stop()
        return bail

    dispatcher = VerbDispatcher(
        permissions=permissions, rcd=rcd, downloads_dir=downloads_dir,
    )

    async def handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        return await dispatcher.dispatch(verb, args)

    server = await serve_rpc(broker_socket, handler)
    log.info("listening on %s (permissions=%s)", broker_socket, permissions)
    print_ready()

    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, shutdown.set)

    async with server:
        serve_task = asyncio.create_task(server.serve_forever(), name="rclone-broker-serve")
        await shutdown.wait()
        log.info("shutting down")
        serve_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await serve_task

    # Capture any mutated session state and push to the supervisor before
    # rcd dies and the state goes with it.
    await _checkpoint(
        rcd=rcd,
        app_sock_path=app_sock_path,
        integration_id=integration_id,
        initial_cookies=cookies,
        initial_client_id=initial_client_id or "",
    )
    await rcd.stop()
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
