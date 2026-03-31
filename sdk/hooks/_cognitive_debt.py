"""CognitiveDebtTracker hook — tracks wasted effort and escalating intervention needs."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class DebtLevel(Enum):
    """Severity levels for cognitive debt."""

    NONE = auto()
    WARNING = auto()
    CONCERNING = auto()
    CRITICAL = auto()


@dataclass
class DebtThresholds:
    """Thresholds for debt level classification."""

    warning: float = 0.3  # 30% debt ratio
    concerning: float = 0.6  # 60% debt ratio
    critical: float = 0.85  # 85% debt ratio


@dataclass
class DebtItem:
    """Record of a specific debt-inducing event."""

    timestamp: datetime
    debt_type: str  # "repetitive_call", "similar_call", "failed_result", "empty_result"
    tool_name: str
    debt_amount: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class InterventionRecord:
    """Record of an intervention that was triggered."""

    timestamp: datetime
    intervention_type: str
    debt_at_intervention: float
    reason: str


class CognitiveDebtTracker:
    """Tracks wasted effort and escalating intervention needs.

    Accumulates "debt" when the agent wastes effort on repetitive or
    unproductive operations. The debt score increases with repetitive
    patterns and decreases with novel, productive actions.

    Attributes:
        debt_score: Current cognitive debt score (0.0-1.0).
        thresholds: DebtThresholds for level classification.
        debt_items: History of individual debt events.
        intervention_history: History of interventions triggered.
    """

    # Debt accumulation rules (configurable)
    DEBT_IDENTICAL_REPEAT = 0.2  # +0.2 per identical repetition
    DEBT_SIMILAR_REPEAT = 0.1  # +0.1 per similar repetition
    DEBT_FAILED_RESULT = 0.15  # +0.15 for errors
    DEBT_EMPTY_RESULT = 0.1  # +0.1 for empty results
    DEBT_NOVEL_ACTION = -0.1  # -0.1 for novel actions (reward)
    DEBT_PROGRESS_MADE = -0.15  # -0.15 for clear progress

    def __init__(self, thresholds: DebtThresholds | None = None) -> None:
        """Initialize the cognitive debt tracker.

        Args:
            thresholds: Thresholds for debt level classification.
                       Uses defaults if not provided.
        """
        self.thresholds = thresholds or DebtThresholds()
        self.debt_score: float = 0.0
        self.debt_items: deque[DebtItem] = deque(maxlen=100)
        self.intervention_history: list[InterventionRecord] = []

        # Pattern tracking
        self._tool_call_history: deque[dict[str, Any]] = deque(maxlen=50)
        self._result_history: deque[str] = deque(maxlen=50)
        self._successful_outcomes: int = 0
        self._total_calls: int = 0

    def add_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: str,
        was_successful: bool = True,
    ) -> float:
        """Record a tool call and update debt based on its characteristics.

        Args:
            tool_name: Name of the tool that was called.
            arguments: Arguments passed to the tool.
            result: Result string from the tool.
            was_successful: Whether the call was successful.

        Returns:
            The debt change for this call (can be negative for progress).
        """
        self._total_calls += 1

        if was_successful:
            self._successful_outcomes += 1

        # Check for repetition patterns
        call_sig = {"tool_name": tool_name, "arguments": arguments}
        debt_change = self._calculate_debt_change(call_sig, result, was_successful)

        # Update debt score
        self.debt_score = max(0.0, min(1.0, self.debt_score + debt_change))

        # Record debt item if significant
        if abs(debt_change) >= 0.05:
            debt_type = self._classify_debt_type(call_sig, result, was_successful)
            item = DebtItem(
                timestamp=datetime.now(timezone.utc),
                debt_type=debt_type,
                tool_name=tool_name,
                debt_amount=debt_change,
                details={
                    "arguments": arguments,
                    "result_preview": result[:200] if len(result) > 200 else result,
                },
            )
            self.debt_items.append(item)

        # Update history
        self._tool_call_history.append(call_sig)
        self._result_history.append(hash(result) % 10000)  # Simple hash

        return debt_change

    def _calculate_debt_change(
        self, call_sig: dict[str, Any], result: str, was_successful: bool
    ) -> float:
        """Calculate debt change for a tool call.

        Args:
            call_sig: Signature of the tool call.
            result: Result string.
            was_successful: Whether the call succeeded.

        Returns:
            Debt change amount (positive for debt, negative for progress).
        """
        debt_change = 0.0

        # Check for identical repetition
        identical_count = self._count_identical_repetitions(call_sig)
        if identical_count > 0:
            debt_change += self.DEBT_IDENTICAL_REPEAT * (1 + identical_count * 0.5)
        else:
            # Check for similar (but not identical) repetitions
            similar_count = self._count_similar_repetitions(call_sig)
            if similar_count > 0:
                debt_change += self.DEBT_SIMILAR_REPEAT * similar_count
            else:
                # Novel action - reduce debt
                debt_change += self.DEBT_NOVEL_ACTION

        # Check result quality
        if not was_successful:
            debt_change += self.DEBT_FAILED_RESULT
        elif not result or len(result.strip()) < 10:
            debt_change += self.DEBT_EMPTY_RESULT
        elif len(result) > 100:
            # Substantial result - sign of progress
            debt_change = min(debt_change, debt_change * 0.5)

        return debt_change

    def _count_identical_repetitions(self, call_sig: dict[str, Any]) -> int:
        """Count how many times this exact call signature appears in history."""
        count = 0
        for past in reversed(self._tool_call_history):
            if past == call_sig:
                count += 1
            elif count > 0:
                # Stop counting if we see a different call
                break
        return count

    def _count_similar_repetitions(self, call_sig: dict[str, Any]) -> int:
        """Count how many similar (but not identical) calls appear."""
        count = 0
        for past in self._tool_call_history:
            if self._is_similar(past, call_sig) and past != call_sig:
                count += 1
        return count

    def _is_similar(self, call_a: dict[str, Any], call_b: dict[str, Any]) -> bool:
        """Check if two calls are similar (same tool, similar args)."""
        if call_a.get("tool_name") != call_b.get("tool_name"):
            return False

        args_a = call_a.get("arguments", {})
        args_b = call_b.get("arguments", {})

        # Count matching keys
        if not args_a and not args_b:
            return True
        if not args_a or not args_b:
            return False

        common_keys = set(args_a.keys()) & set(args_b.keys())
        if len(common_keys) < max(len(args_a), len(args_b)) * 0.5:
            return False

        # Check if values are similar
        similar_values = 0
        for key in common_keys:
            if args_a[key] == args_b[key]:
                similar_values += 1

        similarity = similar_values / max(len(args_a), len(args_b))
        return similarity >= 0.7

    def _classify_debt_type(
        self, call_sig: dict[str, Any], result: str, was_successful: bool
    ) -> str:
        """Classify the type of debt event."""
        if not was_successful:
            return "failed_result"
        if not result or len(result.strip()) < 10:
            return "empty_result"
        if self._count_identical_repetitions(call_sig) > 0:
            return "repetitive_call"
        if self._count_similar_repetitions(call_sig) > 0:
            return "similar_call"
        return "novel_call"

    def get_debt_level(self) -> DebtLevel:
        """Return current debt severity level.

        Returns:
            DebtLevel enum value indicating severity.
        """
        if self.debt_score >= self.thresholds.critical:
            return DebtLevel.CRITICAL
        if self.debt_score >= self.thresholds.concerning:
            return DebtLevel.CONCERNING
        if self.debt_score >= self.thresholds.warning:
            return DebtLevel.WARNING
        return DebtLevel.NONE

    def should_escalate(self) -> bool:
        """Determine if we need stronger intervention.

        Returns:
            True if debt level is CONCERNING or higher.
        """
        return self.get_debt_level() in (DebtLevel.CONCERNING, DebtLevel.CRITICAL)

    def should_stop(self) -> bool:
        """Determine if execution should be stopped.

        Returns:
            True if debt level is CRITICAL.
        """
        return self.get_debt_level() == DebtLevel.CRITICAL

    def record_intervention(self, intervention_type: str, reason: str) -> None:
        """Record that an intervention was triggered.

        Args:
            intervention_type: Type of intervention (nudge, pause, etc.).
            reason: Reason for the intervention.
        """
        record = InterventionRecord(
            timestamp=datetime.now(timezone.utc),
            intervention_type=intervention_type,
            debt_at_intervention=self.debt_score,
            reason=reason,
        )
        self.intervention_history.append(record)
        logger.info(
            "Intervention recorded: %s at debt %.2f - %s",
            intervention_type, self.debt_score, reason,
        )

    def get_metrics(self) -> dict[str, Any]:
        """Return current debt metrics.

        Returns:
            Dictionary with debt score, level, and history.
        """
        return {
            "debt_score": round(self.debt_score, 3),
            "debt_level": self.get_debt_level().name.lower(),
            "thresholds": {
                "warning": self.thresholds.warning,
                "concerning": self.thresholds.concerning,
                "critical": self.thresholds.critical,
            },
            "total_calls": self._total_calls,
            "successful_calls": self._successful_outcomes,
            "recent_debt_items": len(self.debt_items),
            "interventions": len(self.intervention_history),
        }

    def clear(self) -> None:
        """Clear all tracked data and reset debt."""
        self.debt_score = 0.0
        self.debt_items.clear()
        self.intervention_history.clear()
        self._tool_call_history.clear()
        self._result_history.clear()
        self._successful_outcomes = 0
        self._total_calls = 0

    def get_suggestion(self) -> str | None:
        """Generate a suggestion based on current debt patterns.

        Returns:
            A suggestion string or None if no suggestion needed.
        """
        level = self.get_debt_level()
        if level == DebtLevel.NONE:
            return None

        # Analyze recent debt patterns
        recent_items = list(self.debt_items)[-10:]
        if not recent_items:
            return None

        # Count patterns
        repetitive = sum(1 for i in recent_items if i.debt_type == "repetitive_call")
        failed = sum(1 for i in recent_items if i.debt_type == "failed_result")
        empty = sum(1 for i in recent_items if i.debt_type == "empty_result")

        if repetitive >= 3:
            return "You're repeating similar tool calls. Try a different approach or tool."
        if failed >= 2:
            return "Recent tool calls have failed. Consider why they might be failing."
        if empty >= 2:
            return "Tools are returning empty results. The data may not exist."

        if level == DebtLevel.CRITICAL:
            return "Execution appears stuck. Consider completely changing your strategy."
        if level == DebtLevel.CONCERNING:
            return "Progress has slowed. Try a new approach."

        return None