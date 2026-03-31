"""Phase-typed hook system for the tool-call loop.

Each hook phase has its own typed signature — hooks receive exactly what they
need and return exactly what the loop should use to proceed.

Phase signatures:
    on_turn_start(agent_name) -> None
    async before_model(history, iteration, agent_name) -> None
    async after_model(response, history, iteration, agent_name) -> ChatResponse
    before_tool(tool_name, tool_arguments) -> str | None
    after_tool(tool_name, tool_arguments, tool_result) -> str
    on_turn_end(final_content, agent_name) -> None
"""

from ._budget_guard import BudgetGuard
from ._cognitive_debt import CognitiveDebtTracker, DebtLevel, DebtThresholds
from ._context_hook import ContextHook
from ._default import default_hooks
from ._intervention import InterventionConfig, InterventionHook, InterventionLevel
from ._logging_hook import LoggingHook
from ._loop_detector import DetectionResult, LoopDetector
from ._nudge_hook import NudgeHook
from ._persistence import PersistenceHook
from ._progress_aware_hooks import ProgressAwareHooks
from ._progress_tracker import ProgressTracker
from ._scratchpad_hook import ScratchpadHook
from ._stop_hook import StopHook

__all__ = [
    "BudgetGuard",
    "CognitiveDebtTracker",
    "ContextHook",
    "DebtLevel",
    "DebtThresholds",
    "DetectionResult",
    "InterventionConfig",
    "InterventionHook",
    "InterventionLevel",
    "LoggingHook",
    "LoopDetector",
    "NudgeHook",
    "PersistenceHook",
    "ProgressAwareHooks",
    "ProgressTracker",
    "ScratchpadHook",
    "StopHook",
    "default_hooks",
]
