"""Length-prefixed JSON framing over a Unix Domain Socket.

Wire format::

    request : <4-byte BE length><JSON: {"id": n, "verb": "...", "args": {...}}>
    success : <4-byte BE length><JSON: {"id": n, "result": ...}>
    error   : <4-byte BE length><JSON: {"id": n, "error": {"code": "...", "message": "..."}}>

All brokers use this. Access control lives at the filesystem level (socket mode
0660, group ``computron``) — callers get connect/read/write through group
membership; other UIDs get ``EACCES`` on connect.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Every frame starts with a 4-byte big-endian length header so the receiver can
# read exactly the right number of body bytes without hunting for delimiters.
# 4 bytes gives ~4 GiB max; _MAX_FRAME_BYTES below is the real cap.
_LEN_PREFIX_BYTES = 4

# A guardrail against a runaway handler or a malicious peer demanding gigabytes.
# Real payloads are small (UIDs, headers, event notifications); attachments travel
# out-of-band via a side-channel file path rather than inline in frames. 64 MiB is
# more than enough headroom for legitimate frames.
_MAX_FRAME_BYTES = 64 * 1024 * 1024

# A verb handler takes a verb name and its args dict, returns a result dict,
# or raises RpcError for a structured error frame. Anything else is wrapped as
# an INTERNAL error.
VerbHandler = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class RpcError(Exception):
    """Raised by a verb handler to produce a structured error frame.

    The raised code and message are serialized as ``{"error": {"code", "message"}}``
    on the wire. Any other exception becomes ``{"error": {"code": "INTERNAL", ...}}``.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _encode_frame(obj: dict[str, Any]) -> bytes:
    """Serialize ``obj`` into ``<4-byte BE length><JSON body>``.

    Raises ``RpcError("BAD_REQUEST", ...)`` if the encoded body exceeds the
    frame cap — callers in ``_serve_connection`` turn that into an error frame
    so the client gets a response instead of a dropped connection.
    """
    # separators=(",", ":") produces compact JSON (no whitespace between tokens).
    # Nothing reads this by eye; every byte on the wire is worth saving.
    body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    if len(body) > _MAX_FRAME_BYTES:
        msg = "frame exceeds maximum size"
        raise RpcError("BAD_REQUEST", msg)
    # Network byte order (big-endian) is conventional for length-prefixed protocols
    # and matches what non-Python clients would expect if we ever have any.
    return len(body).to_bytes(_LEN_PREFIX_BYTES, "big") + body


async def _read_frame(reader: asyncio.StreamReader) -> dict[str, Any]:
    """Read one frame: the length header, then exactly that many body bytes.

    Uses ``readexactly`` so a truncated header or body becomes an
    ``IncompleteReadError`` the caller can handle as a clean peer-close.
    """
    header = await reader.readexactly(_LEN_PREFIX_BYTES)
    length = int.from_bytes(header, "big")
    # Length validation happens before we try to allocate a huge buffer — we refuse
    # to even read a 3 GiB payload rather than OOM ourselves.
    if length <= 0 or length > _MAX_FRAME_BYTES:
        msg = f"invalid frame length: {length}"
        raise RpcError("BAD_REQUEST", msg)
    body = await reader.readexactly(length)
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        msg = f"malformed JSON: {exc}"
        raise RpcError("BAD_REQUEST", msg) from exc


async def _write_frame(writer: asyncio.StreamWriter, obj: dict[str, Any]) -> None:
    """Encode ``obj`` and push it on the writer. Propagates ``RpcError`` on oversize."""
    writer.write(_encode_frame(obj))
    # drain() applies backpressure: if the peer is slow to read, wait until the
    # send buffer has room rather than queuing unbounded bytes in memory.
    await writer.drain()


async def _serve_connection(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    handler: VerbHandler,
) -> None:
    """Serve RPC frames on one accepted connection until the peer disconnects."""
    try:
        while True:
            # --- read + parse the next request frame ---
            try:
                frame = await _read_frame(reader)
            except asyncio.IncompleteReadError:
                # Clean peer close: half-way through the next frame at EOF.
                return
            except RpcError as exc:
                # Frame-level decode failure (bad length, non-UTF-8, bad JSON).
                # We haven't read a request id yet, so we send an unkeyed error
                # frame and close — the stream is desynced and can't recover.
                await _write_frame(writer, {"error": {"code": exc.code, "message": exc.message}})
                return

            req_id = frame.get("id")
            verb = frame.get("verb")
            args = frame.get("args", {})
            # The handler contract requires these shapes; reject early so the handler
            # doesn't have to defensively check every call.
            if not isinstance(verb, str) or not isinstance(args, dict):
                await _write_frame(
                    writer,
                    {
                        "id": req_id,
                        "error": {"code": "BAD_REQUEST", "message": "missing or malformed verb/args"},
                    },
                )
                continue

            # --- invoke the handler and build the response dict ---
            # Done in two phases: first decide what the response _should_ be, then
            # attempt to send it. Splitting the phases lets us turn a failure in
            # encode-and-send (e.g. oversized result) into a structured error
            # frame instead of an uncaught exception.
            try:
                result = await handler(verb, args)
                response: dict[str, Any] = {"id": req_id, "result": result}
            except RpcError as exc:
                # Handler chose to return a structured error.
                response = {"id": req_id, "error": {"code": exc.code, "message": exc.message}}
            except Exception as exc:
                # Any non-RpcError exception from user code is a programming bug; log
                # with traceback and surface a generic INTERNAL error to the client
                # rather than killing the whole connection over one bad verb call.
                # Intentional catch-all: anything the handler can raise lands here.
                logger.exception("unhandled error in verb handler: %s", verb)
                response = {"id": req_id, "error": {"code": "INTERNAL", "message": str(exc)}}

            # --- send the response, with a fallback for oversized results ---
            try:
                await _write_frame(writer, response)
            except RpcError as exc:
                # _encode_frame tripped the size guard. The handler produced a payload
                # we can't transmit; replace with a structured error so the client
                # knows why rather than seeing the connection drop. The fallback frame
                # is tiny (just the error code + message) so its encode is safe.
                logger.error("failed to encode response for verb %s: %s", verb, exc)
                fallback = {"id": req_id, "error": {"code": exc.code, "message": exc.message}}
                await _write_frame(writer, fallback)
    finally:
        # Always close the socket — even on cancellation or a surprise exception
        # from the exception-handling paths above. Leaking the writer leaves the
        # peer hanging on a read that will never complete.
        writer.close()
        try:
            await writer.wait_closed()
        except (OSError, asyncio.CancelledError):
            # Cleanup-time transport errors are not actionable; log at debug for
            # forensic interest and carry on shutting down.
            logger.debug("wait_closed suppressed", exc_info=True)


async def serve_rpc(
    socket_path: Path | str,
    handler: VerbHandler,
    *,
    socket_mode: int = 0o660,
) -> asyncio.AbstractServer:
    """Bind a UDS listener at ``socket_path`` and serve RPC frames.

    Args:
        socket_path: Filesystem path for the Unix Domain Socket.
        handler: Async callable invoked once per request frame. Return the ``result``
            dict or raise ``RpcError`` for a structured error. Any other exception
            becomes an ``INTERNAL`` error frame.
        socket_mode: chmod applied to the socket file after bind. Default ``0660``
            so the ``computron`` group (app server) can connect; other UIDs can't.

    Returns:
        The asyncio Server. Typical use::

            server = await serve_rpc(path, handler)
            async with server:
                await server.serve_forever()
    """
    path = Path(socket_path)
    # A stale socket from a prior run would make ``start_unix_server`` fail with
    # EADDRINUSE. The supervisor normally unlinks broker sockets on clean shutdown,
    # but a crash or SIGKILL leaves them behind; unlink defensively so the next
    # run starts cleanly.
    if path.exists() or path.is_symlink():
        path.unlink()

    async def _connection_cb(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await _serve_connection(reader, writer, handler)

    server = await asyncio.start_unix_server(_connection_cb, path=str(path))
    # chmod AFTER bind — asyncio.start_unix_server creates the file with the
    # process umask which may be tighter than we want. Setting 0660 explicitly
    # after the fact is the simplest way to guarantee the app server's group
    # can connect.
    path.chmod(socket_mode)
    return server
