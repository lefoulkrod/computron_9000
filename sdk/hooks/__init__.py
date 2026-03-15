"""Phase-typed hook system for the tool-call loop.

Each hook phase has its own typed signature — hooks receive exactly what they
need and return exactly what the loop should use to proceed.

Phase signatures:
    async before_model(history, iteration, agent_name) -> None
    async after_model(response, history, iteration, agent_name) -> ChatResponse
    before_tool(tool_name, tool_arguments) -> str | None
    after_tool(tool_name, tool_arguments, tool_result) -> str
"""

from ._budget_guard import BudgetGuard
from ._context_hook import ContextHook
from ._default import default_hooks
from ._logging_hook import LoggingHook
from ._loop_detector import LoopDetector
from ._nudge_hook import NudgeHook
from ._scratchpad_hook import ScratchpadHook
from ._skill_tracking import SkillTrackingHook
from ._stop_hook import StopHook
from ._turn_recorder import TurnRecorderHook

__all__ = [
    "BudgetGuard",
    "ContextHook",
    "LoggingHook",
    "LoopDetector",
    "NudgeHook",
    "ScratchpadHook",
    "SkillTrackingHook",
    "StopHook",
    "TurnRecorderHook",
    "default_hooks",
]
