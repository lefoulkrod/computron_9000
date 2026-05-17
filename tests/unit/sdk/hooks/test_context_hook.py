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
async def test_after_model_calls_manager_and_returns_response():
    class FakeCtxManager:
        called_with: dict[str, Any] | None = None

        async def after_model(self, **kwargs: Any) -> None:
            self.called_with = kwargs

    mgr = FakeCtxManager()
    hook = ContextHook(mgr, max_iterations=7)
    sentinel = object()
    result = await hook.after_model(sentinel, _FakeHistory(), 3, "TEST")
    assert result is sentinel
    assert mgr.called_with == {"iteration": 3, "max_iterations": 7}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_before_model_delegates_to_manager():
    class FakeCtxManager:
        applied = False

        async def before_model(self) -> None:
            self.applied = True

    mgr = FakeCtxManager()
    hook = ContextHook(mgr)
    await hook.before_model(_FakeHistory(), 1, "TEST")
    assert mgr.applied
