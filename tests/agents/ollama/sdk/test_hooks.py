"""Tests for the phase-typed hook system."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from agents.ollama.sdk.hooks import (
    BudgetGuard,
    ContextHook,
    LoggingHook,
    LoopDetector,
    StopHook,
    default_hooks,
)


class _FakeHistory:
    """Minimal stand-in for ConversationHistory in hook tests."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def append(self, msg: dict[str, Any]) -> None:
        self.messages.append(msg)


class TestBudgetGuard:
    """BudgetGuard appends a nudge message after max_iterations."""

    @pytest.mark.unit
    def test_no_action_within_budget(self):
        guard = BudgetGuard(5)
        history = _FakeHistory()
        guard.before_model(history, 3, "TEST")
        assert len(history.messages) == 0

    @pytest.mark.unit
    def test_triggers_at_limit(self):
        guard = BudgetGuard(3)
        history = _FakeHistory()
        guard.before_model(history, 4, "TEST")
        assert any("budget exhausted" in m["content"].lower() for m in history.messages)

    @pytest.mark.unit
    def test_only_triggers_once(self):
        guard = BudgetGuard(2)
        history1 = _FakeHistory()
        guard.before_model(history1, 3, "TEST")
        assert len(history1.messages) == 1  # nudge injected
        # Second time: no mutation
        history2 = _FakeHistory()
        guard.before_model(history2, 4, "TEST")
        assert len(history2.messages) == 0  # nothing injected

    @pytest.mark.unit
    def test_disabled_when_zero(self):
        guard = BudgetGuard(0)
        history = _FakeHistory()
        guard.before_model(history, 100, "TEST")
        assert len(history.messages) == 0


class TestLoopDetector:
    """LoopDetector catches repeated identical tool calls across rounds."""

    @pytest.mark.unit
    def test_no_action_for_different_calls(self):
        detector = LoopDetector(threshold=3)
        history = _FakeHistory()
        # Round 1
        detector.after_tool("tool_a", {"x": 1}, {"result": "ok"})
        detector.before_model(history, 2, "TEST")
        # Round 2
        detector.after_tool("tool_a", {"x": 2}, {"result": "ok"})
        detector.before_model(history, 3, "TEST")
        # Round 3
        detector.after_tool("tool_b", {"x": 1}, {"result": "ok"})
        detector.before_model(history, 4, "TEST")
        assert len(history.messages) == 0  # no nudge

    @pytest.mark.unit
    def test_triggers_on_repeated_calls(self):
        detector = LoopDetector(threshold=3)
        history = _FakeHistory()
        # 3 identical rounds
        for i in range(3):
            detector.after_tool("echo", {"x": 1}, {"result": "ok"})
            detector.before_model(history, i + 2, "TEST")
        assert any("repeating" in m["content"].lower() for m in history.messages)

    @pytest.mark.unit
    def test_resets_after_trigger(self):
        detector = LoopDetector(threshold=3)
        history = _FakeHistory()
        for i in range(3):
            detector.after_tool("echo", {"x": 1}, {"result": "ok"})
            detector.before_model(history, i + 2, "TEST")
        # Should not trigger again immediately
        detector.after_tool("echo", {"x": 1}, {"result": "ok"})
        history2 = _FakeHistory()
        detector.before_model(history2, 5, "TEST")
        assert len(history2.messages) == 0  # no nudge

    @pytest.mark.unit
    def test_no_action_when_no_tools_called(self):
        detector = LoopDetector(threshold=3)
        history = _FakeHistory()
        detector.before_model(history, 1, "TEST")
        assert len(history.messages) == 0

    @pytest.mark.unit
    def test_after_tool_returns_result_unchanged(self):
        detector = LoopDetector(threshold=3)
        result = {"result": "hello"}
        assert detector.after_tool("t", {}, result) is result


class TestStopHook:
    """StopHook raises StopRequestedError when stop is requested."""

    @pytest.mark.unit
    def test_before_model_raises_on_stop(self):
        from agents.ollama.sdk.events import StopRequestedError

        hook = StopHook()
        with patch("agents.ollama.sdk.hooks.check_stop", side_effect=StopRequestedError):
            with pytest.raises(StopRequestedError):
                hook.before_model(_FakeHistory(), 1, "TEST")

    @pytest.mark.unit
    def test_before_model_noop_when_not_stopped(self):
        hook = StopHook()
        with patch("agents.ollama.sdk.hooks.check_stop"):
            hook.before_model(_FakeHistory(), 1, "TEST")  # should not raise

    @pytest.mark.unit
    def test_after_model_raises_on_stop(self):
        from agents.ollama.sdk.events import StopRequestedError

        hook = StopHook()

        class _FakeMessage:
            tool_calls = [{"name": "foo"}]

        class _FakeResponse:
            message = _FakeMessage()

        response = _FakeResponse()
        history = _FakeHistory()

        with patch("agents.ollama.sdk.hooks.check_stop", side_effect=StopRequestedError):
            with pytest.raises(StopRequestedError):
                hook.after_model(response, history, 1, "TEST")

        # tool_calls should be stripped
        assert response.message.tool_calls is None
        # stop message should be appended
        assert any("stop" in m["content"].lower() for m in history.messages)

    @pytest.mark.unit
    def test_after_model_returns_response_when_not_stopped(self):
        hook = StopHook()
        sentinel = object()
        with patch("agents.ollama.sdk.hooks.check_stop"):
            result = hook.after_model(sentinel, _FakeHistory(), 1, "TEST")
        assert result is sentinel


class TestBeforeToolHook:
    """before_tool hooks can skip tool execution by returning a dict."""

    @pytest.mark.unit
    def test_skip_tool_returns_dict(self):
        class SkipHook:
            def before_tool(self, tool_name: str, tool_arguments: dict) -> dict | None:
                return {"result": "skipped"}

        hook = SkipHook()
        result = hook.before_tool("x", {})
        assert result == {"result": "skipped"}

    @pytest.mark.unit
    def test_proceed_returns_none(self):
        class PassHook:
            def before_tool(self, tool_name: str, tool_arguments: dict) -> dict | None:
                return None

        hook = PassHook()
        assert hook.before_tool("x", {}) is None


class TestAfterToolHook:
    """after_tool hooks return the (possibly rewritten) tool result."""

    @pytest.mark.unit
    def test_override_result(self):
        class OverrideHook:
            def after_tool(self, tool_name: str, tool_arguments: dict, tool_result: dict) -> dict:
                return {"result": "overridden"}

        hook = OverrideHook()
        assert hook.after_tool("x", {}, {"result": "original"}) == {"result": "overridden"}


class TestContextHook:
    """ContextHook records token usage and returns response unchanged."""

    @pytest.mark.unit
    def test_records_and_returns(self):
        class FakeCtxManager:
            recorded = None

            def record_response(self, response: Any) -> None:
                self.recorded = response

        mgr = FakeCtxManager()
        hook = ContextHook(mgr)
        sentinel = object()
        result = hook.after_model(sentinel, _FakeHistory(), 1, "TEST")
        assert result is sentinel
        assert mgr.recorded is sentinel


class TestDefaultHooks:
    """default_hooks() factory."""

    @pytest.mark.unit
    def test_includes_loop_detector(self):
        hooks = default_hooks(None)
        assert any(isinstance(h, LoopDetector) for h in hooks)

    @pytest.mark.unit
    def test_includes_budget_when_nonzero(self):
        hooks = default_hooks(None, max_iterations=10)
        assert any(isinstance(h, BudgetGuard) for h in hooks)

    @pytest.mark.unit
    def test_no_budget_when_zero(self):
        hooks = default_hooks(None, max_iterations=0)
        assert not any(isinstance(h, BudgetGuard) for h in hooks)

    @pytest.mark.unit
    def test_includes_logging_hook(self):
        hooks = default_hooks(None)
        assert any(isinstance(h, LoggingHook) for h in hooks)

    @pytest.mark.unit
    def test_includes_context_hook_when_provided(self):
        class FakeCtxManager:
            def record_response(self, response: Any) -> None:
                pass

        hooks = default_hooks(None, ctx_manager=FakeCtxManager())
        assert any(isinstance(h, ContextHook) for h in hooks)

    @pytest.mark.unit
    def test_no_context_hook_when_none(self):
        hooks = default_hooks(None)
        assert not any(isinstance(h, ContextHook) for h in hooks)
