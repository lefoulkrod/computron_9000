"""Tests for ContextHook."""

from __future__ import annotations

from typing import Any

import pytest

from sdk.hooks import ContextHook


class _FakeHistory:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def append(self, msg: dict[str, Any]) -> None:
        self.messages.append(msg)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_after_model_records_and_returns():
    """after_model calls record_response and returns the response unchanged."""

    class FakeCtxManager:
        recorded = None

        async def record_response(self, response: Any) -> None:
            self.recorded = response

    mgr = FakeCtxManager()
    hook = ContextHook(mgr)
    sentinel = object()
    result = await hook.after_model(sentinel, _FakeHistory(), 1, "TEST")
    assert result is sentinel
    assert mgr.recorded is sentinel


@pytest.mark.unit
@pytest.mark.asyncio
async def test_before_model_calls_apply_strategies():
    """before_model calls apply_strategies on the context manager."""

    class FakeCtxManager:
        applied = False

        async def apply_strategies(self) -> None:
            self.applied = True

    mgr = FakeCtxManager()
    hook = ContextHook(mgr)
    await hook.before_model(_FakeHistory(), 1, "TEST")
    assert mgr.applied
