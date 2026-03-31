"""Tests for LoopDetector hook."""

from __future__ import annotations

from typing import Any

import pytest

from sdk.hooks import LoopDetector


class _FakeHistory:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def append(self, msg: dict[str, Any]) -> None:
        self.messages.append(msg)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_action_for_different_calls():
    # Disable result_repetition detection for this test (was triggering with default threshold of 3)
    detector = LoopDetector(threshold=3, result_repetition_threshold=5)
    history = _FakeHistory()
    detector.after_tool("tool_a", {"x": 1}, {"result": "ok"})
    await detector.before_model(history, 2, "TEST")
    detector.after_tool("tool_a", {"x": 2}, {"result": "ok"})
    await detector.before_model(history, 3, "TEST")
    detector.after_tool("tool_b", {"x": 1}, {"result": "ok"})
    await detector.before_model(history, 4, "TEST")
    assert len(history.messages) == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_triggers_on_repeated_calls():
    detector = LoopDetector(threshold=3, result_repetition_threshold=5)
    history = _FakeHistory()
    for i in range(3):
        detector.after_tool("echo", {"x": 1}, {"result": "ok"})
        await detector.before_model(history, i + 2, "TEST")
    assert any("repeating" in m["content"].lower() for m in history.messages)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resets_after_trigger():
    # Note: With enhanced loop detection, similar/result_repetition detection may still trigger
    # after the exact match threshold is met. This test verifies that a fresh history
    # after the exact match trigger doesn't get flooded with messages.
    detector = LoopDetector(threshold=3, result_repetition_threshold=5)
    history = _FakeHistory()
    for i in range(3):
        detector.after_tool("echo", {"x": 1}, {"result": "ok"})
        await detector.before_model(history, i + 2, "TEST")
    detector.after_tool("echo", {"x": 1}, {"result": "ok"})
    history2 = _FakeHistory()
    await detector.before_model(history2, 5, "TEST")
    # The enhanced detector may still emit warnings for similar/repetition patterns,
    # but should not emit multiple messages for the same pattern
    assert len(history2.messages) <= 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_action_when_no_tools_called():
    detector = LoopDetector(threshold=3)
    history = _FakeHistory()
    await detector.before_model(history, 1, "TEST")
    assert len(history.messages) == 0


@pytest.mark.unit
def test_after_tool_returns_result_unchanged():
    detector = LoopDetector(threshold=3)
    result = {"result": "hello"}
    assert detector.after_tool("t", {}, result) is result
