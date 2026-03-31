"""LoopDetector hook — detects repeated tool-call patterns with multiple detection modes."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    """Result of a loop detection check."""

    detected: bool
    detection_type: str | None = None  # "exact", "similar", "result_repetition", "cycle"
    confidence: float = 0.0
    affected_tools: list[str] = field(default_factory=list)
    message: str = ""


class LoopDetector:
    """Enhanced loop detection with multiple detection modes.

    Detects:
    1. Exact match loops (identical tool call sequences)
    2. Semantic similarity loops (similar but not identical calls)
    3. Result-driven loops (same results despite different inputs)
    4. Cyclic patterns (A→B→C→A tool call sequences)

    Attributes:
        exact_threshold: Number of identical rounds to trigger detection.
        similarity_threshold: Similarity score (0.0-1.0) to consider rounds as similar.
        result_repetition_threshold: Number of identical results to trigger detection.
        cycle_threshold: Number of repetitions of a cyclic pattern to trigger.
    """

    def __init__(
        self,
        exact_threshold: int = 10,
        similarity_threshold: float = 0.85,
        result_repetition_threshold: int = 3,
        cycle_threshold: int = 2,
        threshold: int | None = None,
    ) -> None:
        """Initialize the enhanced loop detector.

        Args:
            exact_threshold: Number of identical rounds to trigger detection.
            similarity_threshold: Similarity threshold for semantic matching (0.0-1.0).
            result_repetition_threshold: Number of identical results to trigger detection.
            cycle_threshold: Number of cycle repetitions to trigger detection.
            threshold: Deprecated parameter for backward compatibility. Use exact_threshold.
        """
        # Support legacy threshold parameter for backward compatibility
        if threshold is not None:
            exact_threshold = threshold

        self.exact_threshold = exact_threshold
        self.similarity_threshold = similarity_threshold
        self.result_repetition_threshold = result_repetition_threshold
        self.cycle_threshold = cycle_threshold

        # Tracking state
        self._recent_hashes: list[str] = []
        self._recent_results: list[str] = []
        self._current_round: list[tuple[str, dict[str, Any]]] = []
        self._current_results: list[str] = []
        self._round_signatures: deque[dict] = deque(maxlen=exact_threshold * 2)
        self._lock = asyncio.Lock()

    def after_tool(
        self,
        tool_name: str,
        tool_arguments: dict[str, Any],
        tool_result: Any,
    ) -> Any:
        """Accumulate (tool_name, arguments) pairs and results for the current round."""
        # after_tool is sync — can't await lock. Use list append which is
        # atomic under CPython's GIL for asyncio (single-threaded event loop).
        self._current_round.append((tool_name, tool_arguments))
        # Hash the result for result-driven detection (handle both strings and other types)
        result_str = json.dumps(tool_result, sort_keys=True) if not isinstance(tool_result, str) else tool_result
        result_hash = hashlib.sha256(result_str.encode()).hexdigest()
        self._current_results.append(result_hash)
        return tool_result

    async def before_model(self, history: Any, iteration: int, agent_name: str) -> DetectionResult:
        """Finalize the previous round's signature and check for repetition patterns.

        Args:
            history: The conversation history to modify if loop detected.
            iteration: Current iteration number.
            agent_name: Name of the current agent.

        Returns:
            DetectionResult indicating if and what type of loop was detected.
        """
        async with self._lock:
            if not self._current_round:
                return DetectionResult(detected=False)

            # Compute round signature
            sig_json = json.dumps(self._current_round, sort_keys=True)
            sig_hash = hashlib.sha256(sig_json.encode()).hexdigest()

            # Compute result signature (concatenated hashes of all results)
            result_sig = hashlib.sha256(
                "".join(self._current_results).encode()
            ).hexdigest()

            # Store round signature
            self._recent_hashes.append(sig_hash)
            self._recent_results.append(result_sig)
            self._round_signatures.append({
                "hash": sig_hash,
                "result_hash": result_sig,
                "tools": [tc[0] for tc in self._current_round],
                "args": [tc[1] for tc in self._current_round],
            })

            # Trim old entries
            if len(self._recent_hashes) > self.exact_threshold:
                self._recent_hashes.pop(0)
            if len(self._recent_results) > self.result_repetition_threshold:
                self._recent_results.pop(0)

            # Clear current round
            current_tools = [tc[0] for tc in self._current_round]
            self._current_round = []
            self._current_results = []

            # Check for exact match loop
            result = self._check_exact_match(sig_hash, current_tools)
            if result.detected:
                await self._apply_intervention(history, result, agent_name)
                return result

            # Check for similar rounds
            result = self._check_similarity(current_tools)
            if result.detected:
                await self._apply_intervention(history, result, agent_name)
                return result

            # Check for result repetition
            result = self._check_result_repetition(result_sig, current_tools)
            if result.detected:
                await self._apply_intervention(history, result, agent_name)
                return result

            # Check for cyclic patterns
            result = self._detect_cycle()
            if result.detected:
                await self._apply_intervention(history, result, agent_name)
                return result

            return DetectionResult(detected=False)

    def _check_exact_match(self, sig_hash: str, tools: list[str]) -> DetectionResult:
        """Check if the same exact signature has been repeated."""
        if (
            len(self._recent_hashes) == self.exact_threshold
            and len(set(self._recent_hashes)) == 1
        ):
            return DetectionResult(
                detected=True,
                detection_type="exact",
                confidence=1.0,
                affected_tools=tools,
                message=f"Exact same tool call repeated {self.exact_threshold} times",
            )
        return DetectionResult(detected=False)

    def _check_similarity(self, current_tools: list[str]) -> DetectionResult:
        """Check for similar (but not identical) rounds."""
        if len(self._round_signatures) < 3:
            return DetectionResult(detected=False)

        # Compare recent round with previous rounds
        recent = self._round_signatures[-1]
        similarities: list[float] = []

        for prev in list(self._round_signatures)[:-1]:
            sim = self._calculate_similarity(recent, prev)
            similarities.append(sim)

        # Check if consistently similar but not identical
        similar_count = sum(1 for s in similarities if s >= self.similarity_threshold)
        if similar_count >= self.exact_threshold - 1:
            avg_sim = sum(similarities) / len(similarities) if similarities else 0
            return DetectionResult(
                detected=True,
                detection_type="similar",
                confidence=avg_sim,
                affected_tools=current_tools,
                message=f"Similar tool calls detected ({avg_sim:.2%} similarity)",
            )
        return DetectionResult(detected=False)

    def _check_result_repetition(self, result_sig: str, tools: list[str]) -> DetectionResult:
        """Check if we're getting identical results despite different inputs."""
        if (
            len(self._recent_results) == self.result_repetition_threshold
            and len(set(self._recent_results)) == 1
        ):
            return DetectionResult(
                detected=True,
                detection_type="result_repetition",
                confidence=1.0,
                affected_tools=tools,
                message=f"Identical results received {self.result_repetition_threshold} times",
            )
        return DetectionResult(detected=False)

    def _calculate_similarity(self, round_a: dict, round_b: dict) -> float:
        """Calculate Jaccard similarity between two round signatures.

        Args:
            round_a: First round signature dict.
            round_b: Second round signature dict.

        Returns:
            Similarity score between 0.0 and 1.0.
        """
        tools_a = set(round_a.get("tools", []))
        tools_b = set(round_b.get("tools", []))

        # Jaccard similarity on tool names
        if not tools_a and not tools_b:
            return 1.0

        intersection = len(tools_a & tools_b)
        union = len(tools_a | tools_b)
        tool_sim = intersection / union if union > 0 else 0.0

        # Also compare arguments (simplified)
        args_a = [json.dumps(a, sort_keys=True) for a in round_a.get("args", [])]
        args_b = [json.dumps(a, sort_keys=True) for a in round_b.get("args", [])]
        set_a = set(args_a)
        set_b = set(args_b)

        if not set_a and not set_b:
            arg_sim = 1.0
        else:
            intersection = len(set_a & set_b)
            union = len(set_a | set_b)
            arg_sim = intersection / union if union > 0 else 0.0

        # Average of tool and argument similarity
        return (tool_sim + arg_sim) / 2.0

    def _detect_cycle(self) -> DetectionResult:
        """Detect cyclic patterns in tool call sequences (e.g., A→B→C→A)."""
        signatures = list(self._round_signatures)
        if len(signatures) < 4:
            return DetectionResult(detected=False)

        # Look for repeating patterns of various lengths
        for cycle_len in range(2, min(5, len(signatures) // 2 + 1)):
            # Take the last cycle_len signatures
            recent_pattern = signatures[-cycle_len:]
            prev_pattern = signatures[-(cycle_len * 2) : -cycle_len]

            if len(prev_pattern) < cycle_len:
                continue

            # Compare patterns
            matches = all(
                recent_pattern[i]["hash"] == prev_pattern[i]["hash"]
                for i in range(cycle_len)
            )

            if matches:
                tools = recent_pattern[0].get("tools", [])
                return DetectionResult(
                    detected=True,
                    detection_type="cycle",
                    confidence=0.9,
                    affected_tools=tools,
                    message=f"Cyclic pattern detected (length {cycle_len})",
                )

        return DetectionResult(detected=False)

    async def _apply_intervention(
        self, history: Any, result: DetectionResult, agent_name: str
    ) -> None:
        """Apply appropriate intervention based on detection result.

        Args:
            history: The conversation history to modify.
            result: The detection result containing loop information.
            agent_name: Name of the current agent.
        """
        logger.warning(
            "Agent '%s' %s: %s",
            agent_name,
            result.detection_type,
            result.message,
        )

        # Clear detection state
        self._recent_hashes.clear()
        self._recent_results.clear()

        # Build contextual nudge message
        base_message = (
            f"Loop detected ({result.detection_type}): {result.message}. "
            "You are repeating tool calls without making progress. "
        )

        # Add specific advice based on detection type
        if result.detection_type == "exact":
            advice = (
                "Try a completely different approach or tool. "
                "The current strategy is not working."
            )
        elif result.detection_type == "similar":
            advice = (
                "Your tool calls are very similar but not identical. "
                "Try changing your arguments more significantly or use a different tool."
            )
        elif result.detection_type == "result_repetition":
            advice = (
                "You're receiving the same results repeatedly. "
                "The data may not exist or you may need to try a different query."
            )
        elif result.detection_type == "cycle":
            advice = (
                "You've entered a cycle of tool calls (A→B→C→A). "
                "Break the pattern by taking a different action or reconsidering your approach."
            )
        else:
            advice = "Try a different approach or move on to the next step."

        history.append({
            "role": "user",
            "content": base_message + advice,
        })

    def clear(self) -> None:
        """Clear all detection state."""
        self._recent_hashes.clear()
        self._recent_results.clear()
        self._round_signatures.clear()
        self._current_round = []
        self._current_results = []
