"""Unit tests for the lazy-load retry behavior in ``tools.integrations._state``.

The cache loads on first read by spawning a future that calls
``refresh_registered_integrations``. If that first call fails — typically
because the supervisor's UDS isn't bound yet during a cold container start —
``_load_future`` must be cleared so subsequent readers retry instead of
silently returning an empty cache for the lifetime of the process.
"""

from __future__ import annotations

import asyncio

import pytest

from tools.integrations import _state


@pytest.fixture(autouse=True)
def _reset_state():
    """Wipe module-level cache state so tests don't pollute each other."""
    _state._registered.clear()
    _state._load_future = None
    yield
    _state._registered.clear()
    _state._load_future = None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_loaded_clears_future_when_supervisor_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed first load shouldn't permanently lock the cache empty.

    Simulates the cold-start race: app fires the load before the supervisor
    has bound ``app.sock`` → ``open_unix_connection`` raises
    ``FileNotFoundError`` → the helper logs a warning and returns. The
    ``_load_future`` must end up ``None`` so the next reader can retry.
    """
    async def _fail(_path: str) -> None:
        raise FileNotFoundError("supervisor not yet bound")

    monkeypatch.setattr(asyncio, "open_unix_connection", _fail)

    await _state._ensure_loaded()
    assert _state._load_future is None
    assert _state._registered == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_loaded_retries_after_failed_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two ``_ensure_loaded`` calls back-to-back when the supervisor is
    unreachable should each *attempt* the connection — not silently reuse
    the cached failure from the first attempt.
    """
    call_count = 0

    async def _fail(_path: str) -> None:
        nonlocal call_count
        call_count += 1
        raise FileNotFoundError("supervisor not yet bound")

    monkeypatch.setattr(asyncio, "open_unix_connection", _fail)

    await _state._ensure_loaded()
    await _state._ensure_loaded()
    assert call_count == 2
    assert _state._load_future is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_loaded_caches_successful_empty_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful load that returns zero integrations is *not* a failure
    and should NOT trigger retries on every subsequent call. The future
    stays done; the cache stays empty until something explicitly mutates.
    """
    call_count = 0

    async def _empty_supervisor(_path: str):
        nonlocal call_count
        call_count += 1
        return _FakeReader(b'{"id": 1, "result": {"integrations": []}}'), _FakeWriter()

    monkeypatch.setattr(asyncio, "open_unix_connection", _empty_supervisor)

    await _state._ensure_loaded()
    await _state._ensure_loaded()
    # Successful load → future cached, no retry on second call.
    assert call_count == 1
    assert _state._load_future is not None
    assert _state._load_future.done()
    assert _state._registered == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_loaded_clears_future_on_supervisor_error_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Supervisor reachable but returns ``{"error": ...}`` → also a failure
    that should clear the future so the next reader retries (the supervisor
    might recover from a transient internal error by the next attempt).
    """
    async def _supervisor_errors(_path: str):
        return _FakeReader(b'{"id": 1, "error": {"code": "INTERNAL", "message": "boom"}}'), _FakeWriter()

    monkeypatch.setattr(asyncio, "open_unix_connection", _supervisor_errors)

    await _state._ensure_loaded()
    assert _state._load_future is None


# ── Test helpers ────────────────────────────────────────────────────────────


class _FakeReader:
    """Minimal async reader that returns one length-prefixed JSON frame."""

    def __init__(self, body: bytes) -> None:
        self._frames = [
            len(body).to_bytes(4, "big"),
            body,
        ]

    async def readexactly(self, n: int) -> bytes:
        chunk = self._frames.pop(0)
        assert len(chunk) == n, f"expected {n} bytes, frame has {len(chunk)}"
        return chunk


class _FakeWriter:
    """Minimal async writer that swallows everything."""

    def write(self, _data: bytes) -> None:
        pass

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass
