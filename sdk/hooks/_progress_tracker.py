"""ProgressTracker hook — tracks execution patterns and progress metrics over time."""

from __future__ import annotations

import hashlib
import json
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRecord:
    """Record of a single tool call within a round."""

    tool_name: str
    arguments: dict[str, Any]
    result_hash: str | None = None

    def to_signature(self) -> dict[str, Any]:
        """Return a serializable signature for this tool call."""
        return {"tool_name": self.tool_name, "arguments": self.arguments}


@dataclass
class RoundRecord:
    """Record of a complete tool call round."""

    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    result_hash: str | None = None

    def compute_hash(self) -> str:
        """Compute a hash of this round's tool calls."""
        sig_data = [
            {"tool_name": tc.tool_name, "arguments": tc.arguments}
            for tc in self.tool_calls
        ]
        sig_json = json.dumps(sig_data, sort_keys=True)
        return hashlib.sha256(sig_json.encode()).hexdigest()


class ProgressTracker:
    """Tracks execution patterns and progress metrics over time.

    This hook monitors tool call patterns, detects result changes,
    and calculates progress scores and cognitive debt metrics.

    Attributes:
        window_size: Number of recent rounds to keep in memory.
        progress_score: Current progress score (0.0-1.0).
        cognitive_debt: Accumulated debt from repetitive operations (0.0+).
    """

    def __init__(self, window_size: int = 20) -> None:
        """Initialize the progress tracker.

        Args:
            window_size: Number of recent rounds to track for metrics calculation.
        """
        self.window_size = window_size
        self._rounds: deque[RoundRecord] = deque(maxlen=window_size)
        self._current_round = RoundRecord()
        self._tool_call_counts: dict[str, int] = {}
        self._result_hashes: deque[str] = deque(maxlen=window_size)

        # Metrics
        self.progress_score: float = 1.0
        self.cognitive_debt: float = 0.0
        self._total_tool_calls: int = 0
        self._novel_tool_calls: int = 0

    def after_tool(
        self,
        tool_name: str,
        tool_arguments: dict[str, Any],
        tool_result: str,
    ) -> str:
        """Accumulate tool call data for the current round.

        Args:
            tool_name: Name of the tool being called.
            tool_arguments: Arguments passed to the tool.
            tool_result: Result string from the tool execution.

        Returns:
            The tool result unchanged.
        """
        # Hash the result to detect if outputs are changing
        result_hash = hashlib.sha256(tool_result.encode()).hexdigest()

        record = ToolCallRecord(
            tool_name=tool_name,
            arguments=tool_arguments,
            result_hash=result_hash,
        )
        self._current_round.tool_calls.append(record)

        # Track tool call frequency
        self._tool_call_counts[tool_name] = self._tool_call_counts.get(tool_name, 0) + 1
        self._total_tool_calls += 1

        return tool_result

    def _finalize_round(self) -> RoundRecord:
        """Finalize the current round and add it to history.

        Returns:
            The completed round record.
        """
        if self._current_round.tool_calls:
            self._current_round.result_hash = self._current_round.compute_hash()
            round_copy = RoundRecord(
                tool_calls=list(self._current_round.tool_calls),
                result_hash=self._current_round.result_hash,
            )
            self._rounds.append(round_copy)
            self._result_hashes.append(self._current_round.result_hash)

            # Update metrics based on this round
            self._update_metrics(round_copy)

        self._current_round = RoundRecord()
        return self._rounds[-1] if self._rounds else RoundRecord()

    def _update_metrics(self, new_round: RoundRecord) -> None:
        """Update progress score and cognitive debt based on new round.

        Args:
            new_round: The newly completed round to analyze.
        """
        if len(self._rounds) < 2:
            self.progress_score = 1.0
            return

        # Check if this is novel compared to previous rounds
        is_novel = True
        novelty_scores: list[float] = []

        for prev_round in list(self._rounds)[:-1]:  # Exclude current
            similarity = self._calculate_round_similarity(new_round, prev_round)
            novelty_scores.append(similarity)
            if similarity > 0.9:  # Very similar to previous
                is_novel = False

        if is_novel:
            self._novel_tool_calls += 1
            # Reduce cognitive debt when making progress
            self.cognitive_debt = max(0.0, self.cognitive_debt - 0.1)
        else:
            # Increase cognitive debt when repeating
            avg_similarity = sum(novelty_scores) / len(novelty_scores) if novelty_scores else 0.0
            self.cognitive_debt = min(1.0, self.cognitive_debt + 0.05 * avg_similarity)

        # Update progress score based on novelty ratio
        if self._total_tool_calls > 0:
            novelty_ratio = self._novel_tool_calls / self._total_tool_calls
            self.progress_score = novelty_ratio

    def _calculate_round_similarity(self, round_a: RoundRecord, round_b: RoundRecord) -> float:
        """Calculate similarity between two rounds (0.0-1.0).

        Uses Jaccard similarity on tool call signatures.

        Args:
            round_a: First round to compare.
            round_b: Second round to compare.

        Returns:
            Similarity score between 0.0 (completely different) and 1.0 (identical).
        """
        if not round_a.tool_calls or not round_b.tool_calls:
            return 0.0 if not (round_a.tool_calls and round_b.tool_calls) else 0.0

        # Compare tool call signatures
        sigs_a = [json.dumps(tc.to_signature(), sort_keys=True) for tc in round_a.tool_calls]
        sigs_b = [json.dumps(tc.to_signature(), sort_keys=True) for tc in round_b.tool_calls]

        # Jaccard similarity
        set_a = set(sigs_a)
        set_b = set(sigs_b)

        if not set_a and not set_b:
            return 1.0

        intersection = len(set_a & set_b)
        union = len(set_a | set_b)

        return intersection / union if union > 0 else 0.0

    def get_progress_metrics(self) -> dict[str, Any]:
        """Return current progress metrics.

        Returns:
            Dictionary containing progress_score, cognitive_debt, and
            other relevant metrics.
        """
        return {
            "progress_score": round(self.progress_score, 3),
            "cognitive_debt": round(self.cognitive_debt, 3),
            "total_tool_calls": self._total_tool_calls,
            "novel_tool_calls": self._novel_tool_calls,
            "tracked_rounds": len(self._rounds),
            "tool_call_distribution": dict(self._tool_call_counts),
        }

    def get_recent_rounds(self, n: int = 5) -> list[RoundRecord]:
        """Get the n most recent rounds.

        Args:
            n: Number of rounds to return.

        Returns:
            List of recent round records.
        """
        return list(self._rounds)[-n:]

    def clear(self) -> None:
        """Clear all tracked data and reset metrics."""
        self._rounds.clear()
        self._result_hashes.clear()
        self._current_round = RoundRecord()
        self._tool_call_counts.clear()
        self.progress_score = 1.0
        self.cognitive_debt = 0.0
        self._total_tool_calls = 0
        self._novel_tool_calls = 0
