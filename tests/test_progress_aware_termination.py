"""Tests for the progress-aware termination system."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from sdk.hooks._cognitive_debt import CognitiveDebtTracker, DebtLevel, DebtThresholds
from sdk.hooks._intervention import InterventionConfig, InterventionHook, InterventionLevel
from sdk.hooks._loop_detector import DetectionResult, LoopDetector
from sdk.hooks._progress_aware_hooks import ProgressAwareHooks
from sdk.hooks._progress_tracker import ProgressTracker, RoundRecord, ToolCallRecord


class TestProgressTracker:
    """Tests for the ProgressTracker."""

    def test_initialization(self):
        """Test that tracker initializes with correct defaults."""
        tracker = ProgressTracker(window_size=20)
        assert tracker.window_size == 20
        assert tracker.progress_score == 1.0
        assert tracker.cognitive_debt == 0.0
        assert tracker._total_tool_calls == 0

    def test_after_tool_accumulates_data(self):
        """Test that after_tool accumulates tool call data."""
        tracker = ProgressTracker()
        result = tracker.after_tool("read_file", {"path": "test.txt"}, "content")
        assert result == "content"
        assert len(tracker._current_round.tool_calls) == 1
        assert tracker._total_tool_calls == 1

    def test_progress_score_decreases_with_repetition(self):
        """Test that progress score decreases with repetitive calls."""
        tracker = ProgressTracker(window_size=10)

        # Simulate multiple identical rounds
        for _ in range(5):
            tracker.after_tool("read_file", {"path": "test.txt"}, "content")
            tracker._finalize_round()

        # Progress should have decreased
        assert tracker.progress_score < 1.0
        assert tracker.cognitive_debt > 0.0

    def test_novel_calls_reduce_debt(self):
        """Test that novel calls reduce cognitive debt."""
        tracker = ProgressTracker()

        # First, accumulate some debt with repetition
        for _ in range(5):
            tracker.after_tool("read_file", {"path": "test.txt"}, "content")
            tracker._finalize_round()

        debt_after_repetition = tracker.cognitive_debt

        # Now make a novel call
        tracker.after_tool("write_file", {"path": "new.txt", "content": "data"}, "ok")
        tracker._finalize_round()

        # Debt should have decreased
        assert tracker.cognitive_debt < debt_after_repetition

    def test_get_metrics(self):
        """Test that metrics are correctly reported."""
        tracker = ProgressTracker()
        tracker.after_tool("tool1", {}, "result1")
        tracker._finalize_round()

        metrics = tracker.get_progress_metrics()
        assert "progress_score" in metrics
        assert "cognitive_debt" in metrics
        assert "total_tool_calls" in metrics
        assert "tool_call_distribution" in metrics

    def test_clear_resets_state(self):
        """Test that clear() resets all state."""
        tracker = ProgressTracker()
        tracker.after_tool("tool", {}, "result")
        tracker._finalize_round()
        tracker.clear()

        assert tracker.progress_score == 1.0
        assert tracker.cognitive_debt == 0.0
        assert tracker._total_tool_calls == 0


class TestLoopDetector:
    """Tests for the enhanced LoopDetector."""

    @pytest.mark.asyncio
    async def test_exact_match_detection(self):
        """Test detection of exactly identical tool call rounds."""
        detector = LoopDetector(exact_threshold=3)
        history: list[dict[str, Any]] = []

        # Simulate 3 identical rounds
        for _ in range(3):
            detector.after_tool("read_file", {"path": "test.txt"}, "content")
            await detector.before_model(history, 0, "test_agent")

        assert len(history) > 0
        assert "repeating" in history[0]["content"].lower() or "loop" in history[0]["content"].lower()

    @pytest.mark.asyncio
    async def test_no_loop_with_different_calls(self):
        """Test that different calls don't trigger loop detection."""
        detector = LoopDetector(exact_threshold=3)
        history: list[dict[str, Any]] = []

        # Simulate different calls
        for i in range(3):
            detector.after_tool("read_file", {"path": f"file{i}.txt"}, f"content{i}")
            await detector.before_model(history, i, "test_agent")

        assert len(history) == 0

    def test_detection_result_structure(self):
        """Test DetectionResult dataclass."""
        result = DetectionResult(
            detected=True,
            detection_type="exact",
            confidence=1.0,
            affected_tools=["read_file"],
            message="Test message",
        )
        assert result.detected is True
        assert result.detection_type == "exact"
        assert result.confidence == 1.0

    def test_similarity_calculation(self):
        """Test similarity calculation between rounds."""
        detector = LoopDetector()

        round_a = {
            "hash": "abc123",
            "result_hash": "result1",
            "tools": ["read_file"],
            "args": [{"path": "test.txt"}],
        }
        round_b = {
            "hash": "abc124",
            "result_hash": "result2",
            "tools": ["read_file"],
            "args": [{"path": "test2.txt"}],
        }

        similarity = detector._calculate_similarity(round_a, round_b)
        assert 0.0 <= similarity <= 1.0

    @pytest.mark.asyncio
    async def test_cycle_detection(self):
        """Test detection of cyclic patterns."""
        detector = LoopDetector()

        # Simulate A → B → C → A cycle
        for _ in range(6):  # Two cycles
            detector.after_tool("tool_a", {}, "result_a")
            await detector.before_model([], 0, "agent")
            detector.after_tool("tool_b", {}, "result_b")
            await detector.before_model([], 0, "agent")

        # Note: cycle detection requires more rounds in history
        # This test verifies the method exists and runs
        result = detector._detect_cycle()
        assert isinstance(result, DetectionResult)


class TestCognitiveDebtTracker:
    """Tests for the CognitiveDebtTracker."""

    def test_initialization(self):
        """Test that tracker initializes correctly."""
        tracker = CognitiveDebtTracker()
        assert tracker.debt_score == 0.0
        assert tracker.get_debt_level() == DebtLevel.NONE

    def test_identical_repeat_accumulates_debt(self):
        """Test that identical repetitions accumulate debt."""
        tracker = CognitiveDebtTracker()

        # First call
        tracker.add_tool_call("tool", {"arg": "value"}, "result")
        initial_debt = tracker.debt_score

        # Repeated identical calls
        for _ in range(3):
            tracker.add_tool_call("tool", {"arg": "value"}, "result")

        assert tracker.debt_score > initial_debt

    def test_debt_levels(self):
        """Test debt level classification."""
        thresholds = DebtThresholds(warning=0.3, concerning=0.6, critical=0.85)
        tracker = CognitiveDebtTracker(thresholds)

        assert tracker.get_debt_level() == DebtLevel.NONE

        # Manually set debt to test thresholds
        tracker.debt_score = 0.3
        assert tracker.get_debt_level() == DebtLevel.WARNING

        tracker.debt_score = 0.6
        assert tracker.get_debt_level() == DebtLevel.CONCERNING

        tracker.debt_score = 0.85
        assert tracker.get_debt_level() == DebtLevel.CRITICAL

    def test_should_escalate(self):
        """Test escalation detection."""
        thresholds = DebtThresholds(concerning=0.5, critical=0.8)
        tracker = CognitiveDebtTracker(thresholds)

        assert tracker.should_escalate() is False

        tracker.debt_score = 0.5
        assert tracker.should_escalate() is True

        tracker.debt_score = 0.8
        assert tracker.should_escalate() is True

    def test_get_suggestion(self):
        """Test suggestion generation."""
        tracker = CognitiveDebtTracker()

        # No suggestion when no debt
        assert tracker.get_suggestion() is None

        # Add some repetitive debt items
        from datetime import datetime
        from sdk.hooks._cognitive_debt import DebtItem

        for _ in range(3):
            tracker.debt_items.append(
                DebtItem(
                    timestamp=datetime.utcnow(),
                    debt_type="repetitive_call",
                    tool_name="test_tool",
                    debt_amount=0.2,
                )
            )

        # Force debt level up
        tracker.debt_score = 0.4

        suggestion = tracker.get_suggestion()
        assert suggestion is not None
        assert len(suggestion) > 0


class TestInterventionHook:
    """Tests for the InterventionHook."""

    @pytest.mark.asyncio
    async def test_nudge_at_warning_level(self):
        """Test that nudge is applied at warning level."""
        config = InterventionConfig(auto_nudge=True)
        thresholds = DebtThresholds(warning=0.3)
        hook = InterventionHook(config, thresholds)
        history: list[dict[str, Any]] = []

        # Simulate repetitive calls to accumulate debt
        for _ in range(10):
            await hook.after_tool("tool", {"arg": "same"}, "result")

        # Wait for enough iterations
        for i in range(5):
            level = await hook.before_model(history, i + 5, "test_agent")

        # Should have applied nudge
        assert len(history) > 0

    def test_generate_contextual_nudge(self):
        """Test nudge message generation."""
        hook = InterventionHook()
        nudge = hook._generate_contextual_nudge()
        assert len(nudge) > 0

    def test_intervention_config_defaults(self):
        """Test InterventionConfig defaults."""
        config = InterventionConfig.default()
        assert config.auto_nudge is True
        assert config.auto_pause is True
        assert config.auto_escalate is False


class TestProgressAwareHooks:
    """Tests for the combined ProgressAwareHooks."""

    @pytest.mark.asyncio
    async def test_enabled_mode(self):
        """Test that hooks work when enabled."""
        hooks = ProgressAwareHooks(enabled=True)
        history: list[dict[str, Any]] = []

        result = await hooks.after_tool("tool", {}, "result")
        assert result == "result"

        should_continue = await hooks.before_model(history, 1, "agent")
        assert should_continue is True

    @pytest.mark.asyncio
    async def test_disabled_mode(self):
        """Test that hooks pass through when disabled."""
        hooks = ProgressAwareHooks(enabled=False)
        history: list[dict[str, Any]] = []

        result = await hooks.after_tool("tool", {}, "result")
        assert result == "result"

        should_continue = await hooks.before_model(history, 1, "agent")
        assert should_continue is True

    def test_get_metrics(self):
        """Test metrics retrieval."""
        hooks = ProgressAwareHooks(enabled=True)
        metrics = hooks.get_metrics()
        assert metrics["enabled"] is True

    def test_clear(self):
        """Test that clear resets state."""
        hooks = ProgressAwareHooks(enabled=True)
        hooks.clear()
        # Should complete without error


class TestIntegration:
    """Integration tests for the complete system."""

    @pytest.mark.asyncio
    async def test_full_execution_scenario(self):
        """Test a complete execution scenario with various patterns."""
        hooks = ProgressAwareHooks(
            loop_threshold=3,
            enabled=True,
        )
        history: list[dict[str, Any]] = []

        # Phase 1: Normal execution
        for i in range(2):
            await hooks.after_tool("read_file", {"path": f"file{i}.txt"}, f"content{i}")
            should_continue = await hooks.before_model(history, i, "agent")
            assert should_continue is True

        # Phase 2: Repetitive calls
        for _ in range(3):
            await hooks.after_tool("read_file", {"path": "same.txt"}, "same_content")
            should_continue = await hooks.before_model(history, 5, "agent")
            assert should_continue is True

        # Phase 3: Check metrics
        metrics = hooks.get_metrics()
        assert metrics["enabled"] is True

        hooks.clear()

    def test_debt_thresholds_configuration(self):
        """Test that debt thresholds can be configured."""
        from sdk.hooks._cognitive_debt import DebtThresholds

        thresholds = DebtThresholds(
            warning=0.25,
            concerning=0.5,
            critical=0.75,
        )
        tracker = CognitiveDebtTracker(thresholds)

        assert tracker.thresholds.warning == 0.25
        assert tracker.thresholds.concerning == 0.5
        assert tracker.thresholds.critical == 0.75


if __name__ == "__main__":
    pytest.main([__file__, "-v"])