"""One-shot RPC to the supervisor's ``app.sock``.

Mirrors :mod:`integrations.broker_client._call` but targets the supervisor
rather than a broker. The supervisor serves the same length-prefixed JSON
framing, so the wire helpers are identical.

Connection-level failures (``FileNotFoundError``, ``ConnectionRefusedError``,
``OSError``) propagate to the caller so it can choose the right response
(HTTP 503, retry, etc.).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from integrations._rpc import RpcError, read_frame, write_frame
from integrations.supervisor_client._errors import SupervisorError


async def call(
    verb: str,
    args: dict[str, Any],
    *,
    app_sock_path: Path | str,
) -> dict[str, Any]:
    """Invoke ``verb`` on the supervisor and return the result dict.

    Args:
        verb: Supervisor verb (``add``, ``list``, ``resolve``, ``update``,
            ``remove``).
        args: Arguments for the verb; passed through verbatim.
        app_sock_path: Path to the supervisor's ``app.sock``.

    Returns:
        The ``result`` value from the supervisor's response frame.

    Raises:
        SupervisorError: The supervisor returned a structured error.
        FileNotFoundError: ``app.sock`` doesn't exist (supervisor not running).
        ConnectionRefusedError: Socket exists but nobody's listening.
        OSError: Any other connection-level failure (includes ``TimeoutError``
            on 3.11+).
    """
    reader, writer = await asyncio.open_unix_connection(str(app_sock_path))
    try:
        await write_frame(writer, {"id": 1, "verb": verb, "args": args})
        try:
            resp = await read_frame(reader)
        except RpcError as exc:
            raise SupervisorError(exc.code, exc.message) from exc
    finally:
        writer.close()
        await writer.wait_closed()

    if "error" in resp:
        error = resp["error"]
        raise SupervisorError(
            error.get("code", "INTERNAL"),
            error.get("message", ""),
        )
    return resp["result"]
