"""ProgressAwareHooks — combined hook container for progress-aware termination."""

from __future__ import annotations

import logging
from typing import Any

from ._cognitive_debt import CognitiveDebtTracker, DebtThresholds
from ._intervention import InterventionConfig, InterventionHook, InterventionLevel
from ._loop_detector import DetectionResult, LoopDetector
from ._progress_tracker import ProgressTracker

logger = logging.getLogger(__name__)


class ProgressAwareHooks:
    """Combined hook container for progress-aware termination.

    This class combines the ProgressTracker, LoopDetector, CognitiveDebtTracker,
    and InterventionHook into a single easy-to-use interface that provides
    comprehensive progress monitoring and intelligent intervention.

    Attributes:
        progress_tracker: Tracks execution patterns and metrics.
        loop_detector: Detects various loop patterns.
        intervention_hook: Manages progressive interventions.
        enabled: Whether progress tracking is enabled.
    """

    def __init__(
        self,
        loop_threshold: int = 5,
        debt_thresholds: DebtThresholds | None = None,
        intervention_config: InterventionConfig | None = None,
        enabled: bool = True,
    ) -> None:
        """Initialize the progress-aware hooks container.

        Args:
            loop_threshold: Threshold for loop detection.
            debt_thresholds: Thresholds for debt level classification.
            intervention_config: Configuration for interventions.
            enabled: Whether progress tracking is enabled.
        """
        self.enabled = enabled

        if enabled:
            # Use enhanced loop detector with similarity detection
            self.loop_detector = LoopDetector(
                exact_threshold=loop_threshold,
                similarity_threshold=0.85,
                result_repetition_threshold=3,
                cycle_threshold=2,
            )

            # Intervention hook manages debt tracking internally
            self.intervention_hook = InterventionHook(
                config=intervention_config or InterventionConfig.default(),
                thresholds=debt_thresholds,
            )
        else:
            self.loop_detector = None
            self.intervention_hook = None

        logger.debug("ProgressAwareHooks initialized (enabled=%s)", enabled)

    async def after_tool(
        self,
        tool_name: str,
        tool_arguments: dict[str, Any],
        tool_result: str,
    ) -> str:
        """Process tool call result through all trackers.

        Args:
            tool_name: Name of the tool.
            tool_arguments: Tool arguments.
            tool_result: Tool result.

        Returns:
            The tool result (potentially modified by loop detector).
        """
        if not self.enabled:
            return tool_result

        # Let loop detector process first (it may modify result)
        if self.loop_detector:
            tool_result = self.loop_detector.after_tool(
                tool_name, tool_arguments, tool_result
            )

        # Then track in intervention system (includes debt & progress tracking)
        if self.intervention_hook:
            tool_result = await self.intervention_hook.after_tool(
                tool_name, tool_arguments, tool_result
            )

        return tool_result

    async def before_model(self, history: Any, iteration: int, agent_name: str) -> bool:
        """Check for loops and apply interventions before model call.

        Args:
            history: Conversation history to modify if intervention needed.
            iteration: Current iteration number.
            agent_name: Current agent name.

        Returns:
            True if execution should continue, False if stopped.
        """
        if not self.enabled:
            return True

        # Check loop detector first
        if self.loop_detector:
            loop_result = await self.loop_detector.before_model(
                history, iteration, agent_name
            )
            if loop_result.detected:
                # Emit loop detected event
                if self.intervention_hook:
                    self.intervention_hook.emit_loop_detected(
                        detection_type=loop_result.detection_type or "unknown",
                        confidence=loop_result.confidence,
                        affected_tools=loop_result.affected_tools,
                        recommendation="Consider a different approach",
                        severity="high" if loop_result.confidence > 0.9 else "medium",
                    )

        # Then check intervention system
        if self.intervention_hook:
            level = await self.intervention_hook.before_model(history, iteration, agent_name)

            if level == InterventionLevel.STOP:
                logger.warning("ProgressAwareHooks stopping execution due to critical debt")
                return False

        return True

    def get_metrics(self) -> dict[str, Any]:
        """Return combined metrics from all trackers.

        Returns:
            Dictionary with all metrics.
        """
        if not self.enabled or not self.intervention_hook:
            return {"enabled": False}

        return {
            "enabled": True,
            **self.intervention_hook.get_metrics(),
        }

    def clear(self) -> None:
        """Clear all tracking state."""
        if self.loop_detector:
            self.loop_detector.clear()
        if self.intervention_hook:
            self.intervention_hook.clear()
        logger.debug("ProgressAwareHooks state cleared")