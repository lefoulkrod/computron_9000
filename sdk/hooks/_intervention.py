"""Intervention system — manages progressive intervention based on cognitive debt."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from sdk.events import AgentEvent, publish_event
from sdk.events._models import InterventionPayload, ProgressMetricsPayload, LoopDetectedPayload
from ._cognitive_debt import CognitiveDebtTracker, DebtLevel, DebtThresholds
from ._progress_tracker import ProgressTracker

logger = logging.getLogger(__name__)


class InterventionLevel(Enum):
    """Levels of intervention severity."""

    NONE = auto()
    NUDGE = auto()  # Inject helpful prompt
    PAUSE = auto()  # Ask user for guidance
    ESCALATE = auto()  # Trigger reflection agent
    STOP = auto()  # Hard stop with summary


@dataclass
class InterventionConfig:
    """Configuration for the intervention system."""

    auto_nudge: bool = True
    auto_pause: bool = True
    auto_escalate: bool = False  # Disabled by default - requires user confirmation
    max_debt_before_stop: float = 0.95
    min_iterations_before_intervention: int = 3
    nudge_cooldown_iterations: int = 2

    @classmethod
    def default(cls) -> InterventionConfig:
        """Return default configuration."""
        return cls()


class InterventionHook:
    """Manages progressive intervention based on cognitive debt.

    This hook coordinates between the ProgressTracker and CognitiveDebtTracker
    to apply appropriate interventions at the right time.

    Attributes:
        config: Intervention configuration.
        debt_tracker: Cognitive debt tracker instance.
        progress_tracker: Progress tracker instance.
    """

    def __init__(
        self,
        config: InterventionConfig | None = None,
        thresholds: DebtThresholds | None = None,
    ) -> None:
        """Initialize the intervention hook.

        Args:
            config: Intervention configuration. Uses defaults if not provided.
            thresholds: Debt thresholds. Uses defaults if not provided.
        """
        self.config = config or InterventionConfig.default()
        self.debt_tracker = CognitiveDebtTracker(thresholds)
        self.progress_tracker = ProgressTracker()

        # State tracking
        self._intervention_history: deque[dict[str, Any]] = deque(maxlen=10)
        self._last_intervention_iteration: int = -1
        self._nudge_cooldown: int = 0
        self._lock = asyncio.Lock()

    async def after_tool(
        self,
        tool_name: str,
        tool_arguments: dict[str, Any],
        tool_result: str,
    ) -> str:
        """Track tool call in debt tracker.

        Args:
            tool_name: Name of the tool.
            tool_arguments: Tool arguments.
            tool_result: Tool result.

        Returns:
            The tool result unchanged.
        """
        # Update progress tracker
        self.progress_tracker.after_tool(tool_name, tool_arguments, tool_result)

        # Update debt tracker
        self.debt_tracker.add_tool_call(
            tool_name=tool_name,
            arguments=tool_arguments,
            result=tool_result,
            was_successful=len(tool_result) > 0,
        )

        return tool_result

    async def before_model(self, history: Any, iteration: int, agent_name: str) -> InterventionLevel:
        """Check if intervention is needed and apply appropriate level.

        Args:
            history: Conversation history to modify.
            iteration: Current iteration number.
            agent_name: Current agent name.

        Returns:
            The intervention level that was applied.
        """
        async with self._lock:
            # Finalize progress tracker round
            self.progress_tracker._finalize_round()

            # Emit progress metrics event
            self._emit_progress_metrics(iteration, agent_name)

            # Check cooldown
            if self._nudge_cooldown > 0:
                self._nudge_cooldown -= 1
                return InterventionLevel.NONE

            # Check if we should intervene
            if iteration < self.config.min_iterations_before_intervention:
                return InterventionLevel.NONE

            debt_level = self.debt_tracker.get_debt_level()

            # Check for stop condition
            if self.debt_tracker.debt_score >= self.config.max_debt_before_stop:
                await self._apply_stop(history, agent_name)
                return InterventionLevel.STOP

            # Apply appropriate intervention
            if debt_level == DebtLevel.CRITICAL:
                if self.config.auto_escalate:
                    await self._apply_escalate(history, agent_name)
                    return InterventionLevel.ESCALATE
                else:
                    await self._apply_pause(history, agent_name)
                    return InterventionLevel.PAUSE

            elif debt_level == DebtLevel.CONCERNING:
                if self.config.auto_pause:
                    await self._apply_pause(history, agent_name)
                    return InterventionLevel.PAUSE
                elif self.config.auto_nudge:
                    await self._apply_nudge(history, agent_name)
                    return InterventionLevel.NUDGE

            elif debt_level == DebtLevel.WARNING:
                if self.config.auto_nudge:
                    await self._apply_nudge(history, agent_name)
                    return InterventionLevel.NUDGE

            return InterventionLevel.NONE

    def _emit_progress_metrics(self, iteration: int, agent_name: str) -> None:
        """Emit progress metrics event."""
        try:
            metrics = self.progress_tracker.get_progress_metrics()
            debt_metrics = self.debt_tracker.get_metrics()

            # Get recent tool calls summary
            recent_rounds = self.progress_tracker.get_recent_rounds(3)
            recent_calls = []
            for round_record in recent_rounds:
                for tc in round_record.tool_calls:
                    recent_calls.append({
                        "tool": tc.tool_name,
                        "args_preview": str(list(tc.arguments.keys()))[:50],
                    })

            event = AgentEvent(
                payload=ProgressMetricsPayload(
                    type="progress_metrics",
                    progress_score=metrics.get("progress_score", 1.0),
                    cognitive_debt=debt_metrics.get("debt_score", 0.0),
                    debt_level=debt_metrics.get("debt_level", "none"),
                    recent_tool_calls=recent_calls if recent_calls else None,
                    suggestion=self.debt_tracker.get_suggestion(),
                )
            )
            publish_event(event)
        except Exception as e:
            logger.debug("Failed to emit progress metrics: %s", e)

    async def _apply_nudge(self, history: Any, agent_name: str) -> None:
        """Apply a gentle nudge to the agent.

        Args:
            history: Conversation history to modify.
            agent_name: Current agent name.
        """
        nudge = self._generate_contextual_nudge()
        history.append({"role": "user", "content": nudge})

        self.debt_tracker.record_intervention("nudge", "Applied contextual nudge")
        self._intervention_history.append({
            "type": "nudge",
            "agent_name": agent_name,
            "message": nudge,
        })
        self._nudge_cooldown = self.config.nudge_cooldown_iterations

        # Emit intervention event
        self._emit_intervention_event("nudge", nudge)

        logger.info("Applied nudge intervention for agent '%s'", agent_name)

    async def _apply_pause(self, history: Any, agent_name: str) -> None:
        """Pause execution and emit pause event.

        In a full implementation, this would wait for user input.
        For now, we inject a strong message and nudge.

        Args:
            history: Conversation history to modify.
            agent_name: Current agent name.
        """
        message = (
            "⚠️ PROGRESS ALERT: Significant cognitive debt detected. "
            "Your approach may not be working. Consider:\n"
            "1. Taking a completely different approach\n"
            "2. Using different tools\n"
            "3. Asking for clarification if you're stuck\n"
            "4. Moving on to the next step"
        )
        history.append({"role": "user", "content": message})

        self.debt_tracker.record_intervention("pause", message)
        self._intervention_history.append({
            "type": "pause",
            "agent_name": agent_name,
            "message": message,
        })

        # Emit intervention event
        self._emit_intervention_event("pause", message)

        logger.warning("Applied pause intervention for agent '%s'", agent_name)

    async def _apply_escalate(self, history: Any, agent_name: str) -> None:
        """Escalate to reflection agent.

        Args:
            history: Conversation history to modify.
            agent_name: Current agent name.
        """
        # For now, this is a stronger nudge
        # In a full implementation, this would trigger a reflection agent
        message = (
            "🔴 CRITICAL: Execution appears stuck. A reflection agent would analyze "
            "your progress and provide guidance. For now, please:\n"
            "1. Stop the current approach\n"
            "2. Summarize what you've tried\n"
            "3. Consider what might work better"
        )
        history.append({"role": "user", "content": message})

        self.debt_tracker.record_intervention("escalate", "Triggered escalation")
        self._intervention_history.append({
            "type": "escalate",
            "agent_name": agent_name,
            "message": message,
        })

        # Emit intervention event
        self._emit_intervention_event("escalate", message)

        logger.error("Applied escalation intervention for agent '%s'", agent_name)

    async def _apply_stop(self, history: Any, agent_name: str) -> None:
        """Stop execution.

        Args:
            history: Conversation history to modify.
            agent_name: Current agent name.
        """
        message = (
            "🛑 EXECUTION STOPPED: Cognitive debt exceeded maximum threshold. "
            "The agent is not making progress. Please review the conversation "
            "and try a different approach."
        )
        history.append({"role": "user", "content": message})

        self.debt_tracker.record_intervention("stop", "Execution stopped due to critical debt")
        self._intervention_history.append({
            "type": "stop",
            "agent_name": agent_name,
            "message": message,
        })

        # Emit intervention event
        self._emit_intervention_event("stop", message)

        logger.critical("Stopped execution for agent '%s' due to critical debt", agent_name)

    def _generate_contextual_nudge(self) -> str:
        """Generate a helpful nudge based on detected patterns.

        Returns:
            A contextual nudge message.
        """
        # Get suggestion from debt tracker
        suggestion = self.debt_tracker.get_suggestion()
        if suggestion:
            return f"💡 SUGGESTION: {suggestion}"

        # Default nudges
        default_nudges = [
            "Consider if your current approach is working. Try something different if stuck.",
            "Are you making progress? If not, try a different tool or strategy.",
            "If you've tried the same thing multiple times without success, try something new.",
            "Consider breaking down the problem differently or asking for clarification.",
        ]

        # Rotate through default nudges
        import random
        return f"💡 {random.choice(default_nudges)}"

    def _emit_intervention_event(self, intervention_type: str, reason: str) -> None:
        """Emit an intervention event.

        Args:
            intervention_type: Type of intervention.
            reason: Reason for the intervention.
        """
        try:
            event = AgentEvent(
                payload=InterventionPayload(
                    type="intervention",
                    intervention_type=intervention_type,  # type: ignore[arg-type]
                    reason=reason,
                    debt_at_intervention=self.debt_tracker.debt_score,
                )
            )
            publish_event(event)
        except Exception as e:
            logger.debug("Failed to emit intervention event: %s", e)

    def emit_loop_detected(
        self,
        detection_type: str,
        confidence: float,
        affected_tools: list[str],
        recommendation: str,
        severity: str,
    ) -> None:
        """Emit a loop detected event.

        Args:
            detection_type: Type of loop detected.
            confidence: Confidence score.
            affected_tools: Tools involved.
            recommendation: Recommendation for user.
            severity: Severity level.
        """
        try:
            event = AgentEvent(
                payload=LoopDetectedPayload(
                    type="loop_detected",
                    detection_type=detection_type,  # type: ignore[arg-type]
                    confidence=confidence,
                    affected_tools=affected_tools,
                    recommendation=recommendation,
                    severity=severity,  # type: ignore[arg-type]
                )
            )
            publish_event(event)
        except Exception as e:
            logger.debug("Failed to emit loop detected event: %s", e)

    def get_metrics(self) -> dict[str, Any]:
        """Return combined metrics from all trackers.

        Returns:
            Dictionary with combined metrics.
        """
        return {
            "progress": self.progress_tracker.get_progress_metrics(),
            "debt": self.debt_tracker.get_metrics(),
            "interventions": list(self._intervention_history),
        }

    def clear(self) -> None:
        """Clear all state."""
        self.progress_tracker.clear()
        self.debt_tracker.clear()
        self._intervention_history.clear()
        self._last_intervention_iteration = -1
        self._nudge_cooldown = 0