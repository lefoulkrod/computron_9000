"""Lifecycle + RC-API client for an embedded ``rclone rcd`` subprocess.

The broker spawns one ``rclone rcd`` per integration. rcd holds the backend
config and the session-acquired PCS cookies in its own heap; the broker
talks to it over a per-integration Unix socket using rclone's JSON-RPC
``/operations/...`` API. Nothing about the auth state is ever written to a
filesystem path — ``--config /dev/null`` neutralises rclone's normal save
behaviour, and the credential state is injected via ``config/create`` after
startup.

Crash safety: rcd is spawned with ``PR_SET_PDEATHSIG = SIGTERM``, so if the
broker dies for any reason (SIGKILL, segfault, unhandled exception) the
kernel signals rcd directly. No orphans.
"""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import json
import logging
import os
import signal
import time
from pathlib import Path
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

# Linux prctl(2) constants — passing the raw ints avoids depending on a
# python-prctl package being installed in the broker's environment.
_PR_SET_PDEATHSIG = 1


class RcdError(Exception):
    """Anything that goes wrong talking to rcd or managing its lifecycle."""


class RcdAuthError(RcdError):
    """rcd reported an upstream auth rejection (e.g. revoked trust token)."""


def _set_pdeathsig() -> None:
    """preexec_fn for the rcd child — die when the broker (our parent) dies.

    Runs in the forked child after fork() and before execve(). ctypes into
    libc is async-signal-unsafe in a general multi-threaded process, but the
    broker is single-threaded asyncio, so this is fine in practice.
    """
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    rc = libc.prctl(_PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0)
    if rc != 0:
        # No real recovery in preexec_fn; signal the parent via exit code.
        os._exit(127)


async def _wait_for_socket(path: Path, timeout: float) -> None:
    """Poll until ``path`` accepts a UDS connection or the deadline expires."""
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        if path.exists():
            try:
                reader, writer = await asyncio.open_unix_connection(str(path))
            except (OSError, ConnectionRefusedError) as exc:
                last_err = exc
            else:
                writer.close()
                with contextlib.suppress(OSError, asyncio.CancelledError):
                    await writer.wait_closed()
                return
        await asyncio.sleep(0.05)
    msg = f"rcd socket {path} not ready within {timeout:.0f}s"
    if last_err is not None:
        msg = f"{msg} (last error: {last_err})"
    raise RcdError(msg)


class RcdClient:
    """Owns one ``rclone rcd`` subprocess + an HTTP-over-UDS client.

    Lifecycle:

    - :meth:`start` spawns rcd, waits for its socket, and configures the
      ``default`` remote via ``config/create``.
    - :meth:`call` issues a JSON-RPC POST to rcd. Long timeout because the
      first call after rcd starts may block on Apple's PCS device-approval
      prompt (the user has to tap Approve on a trusted device).
    - :meth:`dump_config` returns the current remote config as a dict,
      including any session state rcd has acquired (PCS cookies, refreshed
      tokens).
    - :meth:`stop` SIGTERMs rcd and waits for it to exit.
    """

    # Long enough to cover PCS device-approval taps — the first operation
    # after a cold broker spawn blocks until the user approves on their phone.
    _CALL_TIMEOUT_SECONDS = 180.0

    # Bounded — if rcd doesn't bind its socket within this window something's
    # really wrong (binary missing, --rc-addr unparseable, etc.).
    _READY_TIMEOUT_SECONDS = 15.0

    def __init__(self, *, integration_id: str, socket_path: Path) -> None:
        self._integration_id = integration_id
        self._socket_path = socket_path
        self._proc: asyncio.subprocess.Process | None = None
        self._session: aiohttp.ClientSession | None = None

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    async def start(self, *, remote_name: str, rclone_env: dict[str, str]) -> None:
        """Spawn rcd with the remote's config provided as ``RCLONE_CONFIG_*`` env vars.

        Credentials live only in rcd's ``/proc/<pid>/environ`` (mode 0400,
        broker-uid-only); nothing about the iCloud config is written to a
        filesystem path. ``--config=/dev/null`` neutralises rclone's
        own config-save behaviour — any "save" rclone tries goes to the
        kernel sink.
        """
        # Best-effort: unlink any stale socket from a prior crashed rcd
        # before rcd tries to bind here.
        with contextlib.suppress(FileNotFoundError):
            self._socket_path.unlink()

        # Pass our supplied rclone env into the child's environ. Strip any
        # RCLONE_* that may be inherited from the broker first so the only
        # values rcd sees are the ones we explicitly chose.
        env = {k: v for k, v in os.environ.items() if not k.startswith("RCLONE_")}
        env.update(rclone_env)
        env["RCLONE_CONFIG"] = "/dev/null"

        argv = [
            "rclone", "rcd",
            "--rc-no-auth",
            f"--rc-addr=unix://{self._socket_path}",
            "--config=/dev/null",
            # DEBUG so we see iclouddrive's auth path decisions (PCS check,
            # AccountInfo.Webservices content, etc.) in `docker logs`.
            "--log-level=DEBUG",
        ]
        logger.info("spawning rcd for %s at %s", self._integration_id, self._socket_path)
        # rcd's stderr inherits the broker's so its logs surface in
        # `docker logs` directly. stdout goes to /dev/null because the
        # broker's own stdout is the pipe the supervisor reads for the
        # READY handshake — letting rcd write to that pipe would buffer up
        # or confuse the supervisor.
        self._proc = await asyncio.create_subprocess_exec(
            *argv,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            preexec_fn=_set_pdeathsig,
        )

        try:
            await _wait_for_socket(self._socket_path, timeout=self._READY_TIMEOUT_SECONDS)
        except RcdError:
            await self._terminate()
            raise

        with contextlib.suppress(FileNotFoundError):
            self._socket_path.chmod(0o600)

        connector = aiohttp.UnixConnector(path=str(self._socket_path))
        self._session = aiohttp.ClientSession(connector=connector)

    async def call(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """POST ``params`` to rcd's ``/{endpoint}`` and return the JSON body.

        Raises :class:`RcdAuthError` if the response looks like an upstream
        credential rejection, :class:`RcdError` for any other failure.
        """
        if self._session is None:
            raise RcdError("rcd client not started")
        url = f"http://rcd/{endpoint.lstrip('/')}"
        try:
            async with self._session.post(
                url, json=params or {}, timeout=aiohttp.ClientTimeout(total=self._CALL_TIMEOUT_SECONDS),
            ) as resp:
                body = await resp.text()
                if resp.status == 200:
                    try:
                        return json.loads(body) if body else {}
                    except json.JSONDecodeError as exc:
                        raise RcdError(
                            f"rcd {endpoint!r} returned malformed JSON",
                        ) from exc
                # rcd echoes the request body back in its error response under
                # an ``input`` field — which for config/create includes the
                # plaintext password. Pull out only the ``error`` string so
                # secrets we sent in can't land in logs / exception messages.
                safe = _safe_error_detail(body)
                if _looks_like_auth_failure(safe):
                    raise RcdAuthError(f"rcd {endpoint!r}: {safe}")
                raise RcdError(f"rcd {endpoint!r} HTTP {resp.status}: {safe}")
        except aiohttp.ClientError as exc:
            raise RcdError(f"rcd {endpoint!r} network error: {exc}") from exc
        except TimeoutError as exc:
            raise RcdError(f"rcd {endpoint!r} timed out") from exc

    async def upload_file(
        self,
        *,
        parent_path: str,
        filename: str,
        content: bytes,
        mime_type: str = "application/octet-stream",
    ) -> None:
        """Upload ``content`` to ``default:<parent_path>/<filename>``.

        Uses rclone's ``operations/uploadfile`` multipart endpoint so the
        bytes never touch a filesystem path on either side — the body
        flows through kernel UDS buffers from the broker into rcd's heap.
        """
        if self._session is None:
            raise RcdError("rcd client not started")
        form = aiohttp.FormData()
        form.add_field(
            "file",
            content,
            filename=filename,
            content_type=mime_type or "application/octet-stream",
        )
        url = "http://rcd/operations/uploadfile"
        try:
            async with self._session.post(
                url,
                params={"fs": "default:", "remote": parent_path},
                data=form,
                timeout=aiohttp.ClientTimeout(total=self._CALL_TIMEOUT_SECONDS),
            ) as resp:
                body = await resp.text()
                if resp.status == 200:
                    return
                safe = _safe_error_detail(body)
                if _looks_like_auth_failure(safe):
                    raise RcdAuthError(f"rcd uploadfile: {safe}")
                raise RcdError(f"rcd uploadfile HTTP {resp.status}: {safe}")
        except aiohttp.ClientError as exc:
            raise RcdError(f"rcd uploadfile network error: {exc}") from exc
        except TimeoutError as exc:
            raise RcdError("rcd uploadfile timed out") from exc

    async def dump_remote_params(self, remote_name: str) -> dict[str, Any]:
        """Return the live parameters for ``remote_name``, including session state."""
        result = await self.call("config/dump")
        remote = result.get(remote_name)
        if not isinstance(remote, dict):
            raise RcdError(f"rcd config/dump has no remote {remote_name!r}")
        return remote

    async def stop(self) -> None:
        """SIGTERM rcd, wait for exit, close the HTTP session."""
        if self._session is not None:
            await self._session.close()
            self._session = None
        await self._terminate()
        with contextlib.suppress(FileNotFoundError):
            self._socket_path.unlink()

    async def _terminate(self) -> None:
        proc = self._proc
        if proc is None or proc.returncode is not None:
            self._proc = None
            return
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except TimeoutError:
            proc.kill()
            await proc.wait()
        finally:
            self._proc = None


def _safe_error_detail(body: str) -> str:
    """Extract a log-safe error string from an rcd response body.

    rcd's error-response shape is ``{"error": "<msg>", "input": <request>}``.
    The ``input`` echoes the entire request — including, for ``config/create``,
    the plaintext credentials we just sent in. Surfacing only ``error`` keeps
    that out of logs and exception messages.
    """
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        # Non-JSON body — short generic message. We won't include the raw text
        # because we can't tell whether it might contain secrets.
        return "(rcd returned a non-JSON error body)"
    if isinstance(parsed, dict):
        message = parsed.get("error")
        if isinstance(message, str):
            return message[:500]
    return "(rcd error in unrecognized shape)"


def _looks_like_auth_failure(body: str) -> bool:
    """Heuristic: is this rcd error body about credential rejection?"""
    needle = body.lower()
    return any(
        hint in needle
        for hint in (
            "unauthorized",
            "401",
            "403",
            "invalid credentials",
            "login failed",
            "trust token",
            "auth rejected",
        )
    )
