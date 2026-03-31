"""Factory for the standard set of hooks used by all agents."""

from __future__ import annotations

from typing import Any

from ._budget_guard import BudgetGuard
from ._context_hook import ContextHook
from ._logging_hook import LoggingHook
from ._loop_detector import LoopDetector
from ._nudge_hook import NudgeHook
from ._progress_aware_hooks import ProgressAwareHooks
from ._scratchpad_hook import ScratchpadHook
from ._stop_hook import StopHook


def default_hooks(
    agent: Any,
    *,
    max_iterations: int = 0,
    ctx_manager: Any | None = None,
    enable_progress_tracking: bool = True,
) -> list[Any]:
    """Return the standard set of hooks used by all agents.

    Args:
        agent: The agent instance these hooks are for.
        max_iterations: Maximum number of iterations (0 = unlimited).
        ctx_manager: Optional context manager for context hook.
        enable_progress_tracking: Whether to enable progress-aware hooks.

    Returns:
        List of hooks to use.
    """
    hooks: list[Any] = [NudgeHook(), StopHook()]
    if max_iterations > 0:
        hooks.append(BudgetGuard(max_iterations))

    # Use enhanced progress-aware hooks if enabled
    if enable_progress_tracking:
        hooks.append(
            ProgressAwareHooks(
                loop_threshold=5,
                enabled=True,
            )
        )
    else:
        # Fall back to simple loop detector
        hooks.append(LoopDetector())

    hooks.append(LoggingHook(agent))
    hooks.append(ScratchpadHook())
    if ctx_manager is not None:
        hooks.append(ContextHook(ctx_manager, max_iterations=max_iterations))
    return hooks
