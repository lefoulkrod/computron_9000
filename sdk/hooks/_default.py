"""Factory for the standard set of hooks used by all agents."""

from __future__ import annotations

from typing import Any

from ._budget_guard import BudgetGuard
from ._context_hook import ContextHook
from ._logging_hook import LoggingHook
from ._loop_detector import LoopDetector
from ._nudge_hook import NudgeHook
from ._scratchpad_hook import ScratchpadHook
from ._stop_hook import StopHook


def default_hooks(
    agent: Any,
    *,
    max_iterations: int = 0,
    ctx_manager: Any | None = None,
) -> list[Any]:
    """Return the standard set of hooks used by all agents."""
    hooks: list[Any] = [NudgeHook(), StopHook()]
    if max_iterations > 0:
        hooks.append(BudgetGuard(max_iterations))
    hooks.append(LoopDetector())
    hooks.append(LoggingHook(agent))
    hooks.append(ScratchpadHook())
    if ctx_manager is not None:
        hooks.append(ContextHook(ctx_manager, max_iterations=max_iterations))
    return hooks
