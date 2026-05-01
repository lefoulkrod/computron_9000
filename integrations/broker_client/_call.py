"""The ``call()`` entry point — how app-server code invokes broker verbs.

Two RPC hops in one call:

1. Resolve: ask the supervisor's ``app.sock`` for the broker's UDS path given
   an integration id.
2. Invoke: open the broker's UDS, send the verb frame, read the response.

Each hop uses the same length-prefixed JSON framing the supervisor and
brokers serve. Errors from either hop are mapped to the exception hierarchy
in ``_errors.py``.

Walking-skeleton shape: no resolve-cache, no connection pool, one UDS
connection per ``call()`` invocation. That matches what the existing tests
use and keeps the first pass small; a caching layer slots in later without
touching callers.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from integrations._rpc import RpcError, read_frame, write_frame
from integrations.broker_client._errors import (
    IntegrationAuthFailed,
    IntegrationError,
    IntegrationNotConnected,
    IntegrationWriteDenied,
)


async def call(
    integration_id: str,
    verb: str,
    args: dict[str, Any],
    *,
    app_sock_path: Path,
) -> Any:
    """Invoke ``verb`` on the broker for ``integration_id``.

    Args:
        integration_id: The integration the tool handler is operating on
            (e.g. ``"gmail_personal"``).
        verb: The broker verb to call (e.g. ``"list_mailboxes"``).
        args: Arguments for the verb; passed through verbatim to the broker.
        app_sock_path: Path to the supervisor's ``app.sock``. Required —
            the caller knows where it lives (env var in production, fixture
            in tests).

    Returns:
        Whatever the broker returned in its ``result`` field. The shape
        depends on the verb.

    Raises:
        IntegrationNotConnected: supervisor doesn't know about this integration.
        IntegrationAuthFailed: broker returned ``AUTH``.
        IntegrationWriteDenied: broker returned ``WRITE_DENIED``.
        IntegrationError: any other protocol-level or broker-side failure.
    """
    # --- Hop 1: resolve integration_id -> broker socket via the supervisor.
    resolve_response = await _rpc_one_shot(
        app_sock_path,
        {"id": 1, "verb": "resolve", "args": {"id": integration_id}},
    )
    if "error" in resolve_response:
        error = resolve_response["error"]
        code = error.get("code", "")
        message = error.get("message", "")
        if code == "NOT_FOUND":
            raise IntegrationNotConnected(
                f"integration {integration_id!r}: {message or 'not registered'}",
            )
        # The supervisor raised something else — treat as a generic integration
        # error; callers can special-case later if we start growing varieties.
        raise IntegrationError(
            f"resolve for {integration_id!r} failed: {code}: {message}",
        )

    broker_socket = Path(resolve_response["result"]["socket"])

    # --- Hop 2: call the broker directly.
    broker_response = await _rpc_one_shot(
        broker_socket,
        {"id": 1, "verb": verb, "args": args},
    )
    if "error" in broker_response:
        error = broker_response["error"]
        code = error.get("code", "")
        message = error.get("message", "")
        if code == "AUTH":
            raise IntegrationAuthFailed(f"{integration_id} {verb}: {message}")
        if code == "WRITE_DENIED":
            raise IntegrationWriteDenied(f"{integration_id} {verb}: {message}")
        raise IntegrationError(
            f"{integration_id} {verb} -> {code}: {message}",
        )

    return broker_response["result"]


async def _rpc_one_shot(
    socket_path: Path, frame: dict[str, Any],
) -> dict[str, Any]:
    """Open a UDS, send one frame, read one frame, close.

    Wraps the framing helpers in ``integrations._rpc`` so the two hops above
    aren't repeating the same 8 lines of connection plumbing.
    """
    reader, writer = await asyncio.open_unix_connection(str(socket_path))
    try:
        await write_frame(writer, frame)
        try:
            return await read_frame(reader)
        except RpcError as exc:
            # A malformed response from the broker / supervisor is a protocol
            # bug on their side; surface as a generic error rather than letting
            # an RpcError (which is meant for server-side use) bubble into
            # caller code.
            raise IntegrationError(
                f"malformed response from {socket_path}: {exc.code}: {exc.message}",
            ) from exc
    finally:
        writer.close()
        await writer.wait_closed()
