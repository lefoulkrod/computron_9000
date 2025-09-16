"""Tests for graceful shutdown callback utilities."""

from __future__ import annotations

import pytest

pytest.importorskip("cachetools", reason="utils package requires cachetools")

from utils.shutdown import register_shutdown_callback, run_shutdown_callbacks


@pytest.mark.asyncio
async def test_run_shutdown_callbacks_invokes_callbacks_in_lifo_order():
    events: list[str] = []

    async def async_callback() -> None:
        events.append("async")

    def sync_callback() -> None:
        events.append("sync")

    register_shutdown_callback(async_callback)
    register_shutdown_callback(sync_callback)

    await run_shutdown_callbacks()

    assert events == ["sync", "async"]


@pytest.mark.asyncio
async def test_run_shutdown_callbacks_continues_after_exception():
    events: list[str] = []

    def failing_callback() -> None:
        raise RuntimeError("boom")

    def successful_callback() -> None:
        events.append("ok")

    register_shutdown_callback(successful_callback)
    register_shutdown_callback(failing_callback)

    await run_shutdown_callbacks()

    assert events == ["ok"]
