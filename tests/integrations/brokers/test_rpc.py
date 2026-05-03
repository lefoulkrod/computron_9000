"""Tests for the shared broker RPC layer.

Integration-style — real Unix Domain Socket, real asyncio server, in-process client.
No subprocess here; the RPC module is a pure networking primitive and doesn't care
who's on the other end. Subprocess-based broker tests live in ``test_email.py`` etc.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from integrations import _rpc as rpc_module
from integrations._rpc import RpcError, serve_rpc


async def _send_frame(writer: asyncio.StreamWriter, obj: dict[str, Any]) -> None:
    body = json.dumps(obj).encode("utf-8")
    writer.write(len(body).to_bytes(4, "big") + body)
    await writer.drain()


async def _recv_frame(reader: asyncio.StreamReader) -> dict[str, Any]:
    header = await reader.readexactly(4)
    length = int.from_bytes(header, "big")
    body = await reader.readexactly(length)
    return json.loads(body.decode("utf-8"))


async def _call(socket_path: Path, frame: dict[str, Any]) -> dict[str, Any]:
    """Open a client connection, send one frame, read one frame, close."""
    reader, writer = await asyncio.open_unix_connection(str(socket_path))
    try:
        await _send_frame(writer, frame)
        return await _recv_frame(reader)
    finally:
        writer.close()
        await writer.wait_closed()


@pytest.mark.asyncio
async def test_happy_path_returns_result(tmp_path: Path) -> None:
    """A handler returning a dict round-trips as {id, result}."""
    socket_path = tmp_path / "broker.sock"

    async def handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        assert verb == "echo"
        return {"echoed": args}

    server = await serve_rpc(socket_path, handler)
    async with server:
        response = await _call(socket_path, {"id": 7, "verb": "echo", "args": {"x": 1}})

    assert response == {"id": 7, "result": {"echoed": {"x": 1}}}


@pytest.mark.asyncio
async def test_rpc_error_produces_error_frame(tmp_path: Path) -> None:
    """Handler raising RpcError is serialized as {id, error: {code, message}}."""
    socket_path = tmp_path / "broker.sock"

    async def handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        raise RpcError("AUTH", "nope")

    server = await serve_rpc(socket_path, handler)
    async with server:
        response = await _call(socket_path, {"id": 42, "verb": "x", "args": {}})

    assert response == {"id": 42, "error": {"code": "AUTH", "message": "nope"}}


@pytest.mark.asyncio
async def test_unhandled_exception_becomes_internal_error(tmp_path: Path) -> None:
    """A non-RpcError exception is surfaced as {error: {code: INTERNAL, ...}}."""
    socket_path = tmp_path / "broker.sock"

    async def handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        raise ValueError("kaboom")

    server = await serve_rpc(socket_path, handler)
    async with server:
        response = await _call(socket_path, {"id": 1, "verb": "x", "args": {}})

    assert response == {"id": 1, "error": {"code": "INTERNAL", "message": "kaboom"}}


@pytest.mark.asyncio
async def test_malformed_verb_rejected(tmp_path: Path) -> None:
    """A frame without a string 'verb' key returns BAD_REQUEST."""
    socket_path = tmp_path / "broker.sock"

    async def handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        pytest.fail("handler should not be invoked for malformed frame")
        return {}  # unreachable — pytest.fail raises

    server = await serve_rpc(socket_path, handler)
    async with server:
        response = await _call(socket_path, {"id": 1, "verb": 123, "args": {}})

    assert response == {
        "id": 1,
        "error": {"code": "BAD_REQUEST", "message": "missing or malformed verb/args"},
    }


@pytest.mark.asyncio
async def test_multiple_calls_on_one_connection(tmp_path: Path) -> None:
    """The server keeps reading frames after a response; multiple calls per conn."""
    socket_path = tmp_path / "broker.sock"

    counter = {"n": 0}

    async def handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        counter["n"] += 1
        return {"n": counter["n"]}

    server = await serve_rpc(socket_path, handler)
    async with server:
        reader, writer = await asyncio.open_unix_connection(str(socket_path))
        try:
            for i in range(1, 4):
                await _send_frame(writer, {"id": i, "verb": "inc", "args": {}})
                resp = await _recv_frame(reader)
                assert resp == {"id": i, "result": {"n": i}}
        finally:
            writer.close()
            await writer.wait_closed()


@pytest.mark.asyncio
async def test_stale_socket_file_is_replaced(tmp_path: Path) -> None:
    """A leftover file at the socket path is unlinked before bind."""
    socket_path = tmp_path / "broker.sock"
    socket_path.write_text("stale")  # not a real socket, just a file in the way

    async def handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    server = await serve_rpc(socket_path, handler)
    async with server:
        response = await _call(socket_path, {"id": 1, "verb": "x", "args": {}})

    assert response == {"id": 1, "result": {"ok": True}}


@pytest.mark.asyncio
async def test_oversized_result_becomes_error_frame(tmp_path: Path) -> None:
    """A handler returning a payload bigger than the frame cap yields BAD_REQUEST,
    not a dropped connection.
    """
    socket_path = tmp_path / "broker.sock"

    # Lower the cap so we don't need to allocate 64 MiB to hit the path.
    original_max = rpc_module._MAX_FRAME_BYTES
    rpc_module._MAX_FRAME_BYTES = 128

    async def handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        return {"huge": "x" * 500}   # well over 128 bytes once serialized

    try:
        server = await serve_rpc(socket_path, handler)
        async with server:
            response = await _call(socket_path, {"id": 9, "verb": "x", "args": {}})
    finally:
        rpc_module._MAX_FRAME_BYTES = original_max

    assert response == {
        "id": 9,
        "error": {"code": "BAD_REQUEST", "message": "frame exceeds maximum size"},
    }


@pytest.mark.asyncio
async def test_frame_length_zero_yields_bad_request_and_closes(tmp_path: Path) -> None:
    """A zero-length header is rejected with an unkeyed BAD_REQUEST error,
    after which the server closes the connection (the stream is desynced)."""
    socket_path = tmp_path / "broker.sock"

    async def handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        pytest.fail("handler should not be invoked for bad frame")
        return {}

    server = await serve_rpc(socket_path, handler)
    async with server:
        reader, writer = await asyncio.open_unix_connection(str(socket_path))
        try:
            # Raw 4-byte header with length = 0, no body.
            writer.write((0).to_bytes(4, "big"))
            await writer.drain()
            response = await _recv_frame(reader)
            assert response == {
                "error": {"code": "BAD_REQUEST", "message": "invalid frame length: 0"}
            }
            # Server must close after sending the frame-decode error.
            with pytest.raises(asyncio.IncompleteReadError):
                await reader.readexactly(1)
        finally:
            writer.close()
            await writer.wait_closed()


@pytest.mark.asyncio
async def test_frame_length_over_cap_yields_bad_request_and_closes(tmp_path: Path) -> None:
    """A length header above the frame-size cap is rejected before any body is
    read. Prevents an OOM by refusing to allocate a huge buffer."""
    socket_path = tmp_path / "broker.sock"

    async def handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        pytest.fail("handler should not be invoked for bad frame")
        return {}

    server = await serve_rpc(socket_path, handler)
    async with server:
        reader, writer = await asyncio.open_unix_connection(str(socket_path))
        try:
            oversized = rpc_module._MAX_FRAME_BYTES + 1
            writer.write(oversized.to_bytes(4, "big"))
            # NB: we don't send a body — the server should reject on the header alone.
            await writer.drain()
            response = await _recv_frame(reader)
            assert response == {
                "error": {
                    "code": "BAD_REQUEST",
                    "message": f"invalid frame length: {oversized}",
                }
            }
            with pytest.raises(asyncio.IncompleteReadError):
                await reader.readexactly(1)
        finally:
            writer.close()
            await writer.wait_closed()


@pytest.mark.asyncio
async def test_frame_body_not_json_yields_bad_request_and_closes(tmp_path: Path) -> None:
    """A length header matching a body that isn't valid JSON is rejected."""
    socket_path = tmp_path / "broker.sock"

    async def handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        pytest.fail("handler should not be invoked for bad frame")
        return {}

    server = await serve_rpc(socket_path, handler)
    async with server:
        reader, writer = await asyncio.open_unix_connection(str(socket_path))
        try:
            body = b"not json"
            writer.write(len(body).to_bytes(4, "big") + body)
            await writer.drain()
            response = await _recv_frame(reader)
            assert response == {
                "error": {
                    "code": "BAD_REQUEST",
                    "message": "malformed JSON: Expecting value: line 1 column 1 (char 0)",
                }
            }
            with pytest.raises(asyncio.IncompleteReadError):
                await reader.readexactly(1)
        finally:
            writer.close()
            await writer.wait_closed()


@pytest.mark.asyncio
async def test_socket_mode_applied(tmp_path: Path) -> None:
    """The socket file's permission bits match ``socket_mode``.

    Uses a non-default mode (0o600) so the test actually exercises the parameter —
    asserting on the default would pass even if the parameter were ignored.
    """
    socket_path = tmp_path / "broker.sock"

    async def handler(verb: str, args: dict[str, Any]) -> dict[str, Any]:
        return {}

    server = await serve_rpc(socket_path, handler, socket_mode=0o600)
    async with server:
        mode = socket_path.stat().st_mode & 0o777
        assert mode == 0o600
