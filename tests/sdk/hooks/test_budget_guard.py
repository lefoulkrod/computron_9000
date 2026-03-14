"""Tests for BudgetGuard hook."""

from __future__ import annotations

from typing import Any

import pytest

from sdk.hooks import BudgetGuard


class _FakeHistory:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def append(self, msg: dict[str, Any]) -> None:
        self.messages.append(msg)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_action_within_budget():
    guard = BudgetGuard(5)
    history = _FakeHistory()
    await guard.before_model(history, 3, "TEST")
    assert len(history.messages) == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_triggers_at_limit():
    guard = BudgetGuard(3)
    history = _FakeHistory()
    await guard.before_model(history, 4, "TEST")
    assert any("budget exhausted" in m["content"].lower() for m in history.messages)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_only_triggers_once():
    guard = BudgetGuard(2)
    history1 = _FakeHistory()
    await guard.before_model(history1, 3, "TEST")
    assert len(history1.messages) == 1
    history2 = _FakeHistory()
    await guard.before_model(history2, 4, "TEST")
    assert len(history2.messages) == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_disabled_when_zero():
    guard = BudgetGuard(0)
    history = _FakeHistory()
    await guard.before_model(history, 100, "TEST")
    assert len(history.messages) == 0
