"""Phase-typed hook system for the tool-call loop.

Each hook phase has its own typed signature — hooks receive exactly what they
need and return exactly what the loop should use to proceed.

Phase signatures:
    before_model(history, iteration, agent_name) -> None
    after_model(response, history, iteration, agent_name) -> ChatResponse
    before_tool(tool_name, tool_arguments) -> dict | None
    after_tool(tool_name, tool_arguments, tool_result) -> dict
"""

from __future__ import annotations

import hashlib
import json
import logging
import pprint
from typing import Any

from .events import StopRequestedError, check_stop

logger = logging.getLogger(__name__)


# ── Built-in hooks ───────────────────────────────────────────────────────


class BudgetGuard:
    """Appends a nudge message when the iteration budget is exceeded."""

    def __init__(self, max_iterations: int) -> None:
        """Initialize with the maximum number of iterations allowed."""
        self._max = max_iterations
        self._exhausted = False

    def before_model(self, history: Any, iteration: int, agent_name: str) -> None:
        """Append a budget-exhaustion nudge if over the iteration limit."""
        if self._max <= 0 or self._exhausted:
            return
        if iteration > self._max:
            self._exhausted = True
            logger.warning(
                "Agent '%s' hit max_iterations (%d), forcing stop",
                agent_name,
                self._max,
            )
            history.append({
                "role": "user",
                "content": (
                    f"Tool call budget exhausted ({self._max} iterations). "
                    "Wrap up and respond with the information you have."
                ),
            })


class LoopDetector:
    """Detects when the model repeats the same tool-call signature N rounds in a row."""

    def __init__(self, threshold: int = 3) -> None:
        """Initialize with the number of identical rounds that triggers a nudge."""
        self._threshold = threshold
        self._recent: list[str] = []
        self._current_round: list[tuple[str, dict[str, Any]]] = []

    def after_tool(
        self,
        tool_name: str,
        tool_arguments: dict[str, Any],
        tool_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Accumulate (tool_name, arguments) pairs for the current round."""
        self._current_round.append((tool_name, tool_arguments))
        return tool_result

    def before_model(self, history: Any, iteration: int, agent_name: str) -> None:
        """Finalize the previous round's signature and check for repetition."""
        if not self._current_round:
            return
        sig_json = json.dumps(self._current_round, sort_keys=True)
        sig_hash = hashlib.sha256(sig_json.encode()).hexdigest()
        self._current_round = []
        self._recent.append(sig_hash)
        if len(self._recent) > self._threshold:
            self._recent.pop(0)
        if (
            len(self._recent) == self._threshold
            and len(set(self._recent)) == 1
        ):
            logger.warning(
                "Agent '%s' stuck in loop: same tool call %d times in a row",
                agent_name,
                self._threshold,
            )
            self._recent.clear()
            history.append({
                "role": "user",
                "content": (
                    "You are repeating the same tool call without making progress. "
                    "Try a different approach, use a different tool, or change your arguments. "
                    "If the current approach isn't working, move on to the next step."
                ),
            })


class LoggingHook:
    """Logs model inputs and outputs at debug level."""

    def __init__(self, agent: Any) -> None:
        """Initialize with the agent whose name is used in log lines."""
        self._agent_name: str = getattr(agent, "name", "unknown")

    def before_model(self, history: Any, iteration: int, agent_name: str) -> None:
        """Log the chat history being sent to the model."""
        log_text = (
            f"\n========== [before_model_call] for agent: {self._agent_name} =========="
            f"\nChat history sent to LLM:\n{pprint.pformat(history.messages)}"
        )
        logger.debug("\033[32m%s\033[0m", log_text)

    def after_model(
        self, response: Any, history: Any, iteration: int, agent_name: str
    ) -> Any:
        """Log the model response and runtime stats."""
        log_text = f"\n========== [after_model_call] for agent: {self._agent_name} =========="
        if hasattr(response, "done") and getattr(response, "done", False):
            from agents.ollama.sdk.llm_runtime_stats import llm_runtime_stats

            stats = llm_runtime_stats(response)
            log_text += (
                f"\nLLM stats:\n"
                f"  total_duration:         {getattr(stats, 'total_duration', 0) or 0:.3f}s\n"
                f"  load_duration:          {getattr(stats, 'load_duration', 0) or 0:.3f}s\n"
                f"  prompt_eval_count:      {getattr(stats, 'prompt_eval_count', 0)}\n"
                f"  prompt_eval_duration:   {getattr(stats, 'prompt_eval_duration', 0) or 0:.3f}s\n"
                f"  prompt_tokens_per_sec:  {getattr(stats, 'prompt_tokens_per_sec', 0) or 0:.2f}\n"
                f"  eval_count:             {getattr(stats, 'eval_count', 0)}\n"
                f"  eval_duration:          {getattr(stats, 'eval_duration', 0) or 0:.3f}s\n"
                f"  eval_tokens_per_sec:    {getattr(stats, 'eval_tokens_per_sec', 0) or 0:.2f}\n"
            )
        try:
            response_data = response.model_dump()
            log_text += f"\nLLM response:\n{pprint.pformat(response_data)}"
        except (AttributeError, TypeError, ValueError):
            log_text += "\nLLM response: <model_dump failed>"
        logger.debug("\033[33m%s\033[0m", log_text)
        return response


class StopHook:
    """Checks for user-requested stop at before_model and after_model phases."""

    def before_model(self, history: Any, iteration: int, agent_name: str) -> None:
        """Raise ``StopRequestedError`` if the user requested a stop."""
        check_stop()

    def after_model(
        self, response: Any, history: Any, iteration: int, agent_name: str
    ) -> Any:
        """Strip tool calls and raise ``StopRequestedError`` on stop request."""
        try:
            check_stop()
        except StopRequestedError:
            # Strip tool_calls so the assistant message won't have dangling calls
            if hasattr(response, "message") and hasattr(response.message, "tool_calls"):
                response.message.tool_calls = None
            history.append({
                "role": "user",
                "content": "The user has requested to stop. Wrap up your response.",
            })
            raise
        return response


class ContextHook:
    """Records token usage from model responses via a ContextManager."""

    def __init__(self, ctx_manager: Any) -> None:
        """Initialize with the context manager that tracks token usage."""
        self._ctx_manager = ctx_manager

    def after_model(
        self, response: Any, history: Any, iteration: int, agent_name: str
    ) -> Any:
        """Record token usage from the response."""
        self._ctx_manager.record_response(response)
        return response


# ── Factory ──────────────────────────────────────────────────────────────


def default_hooks(
    agent: Any,
    *,
    max_iterations: int = 0,
    ctx_manager: Any | None = None,
) -> list[Any]:
    """Return the standard set of hooks used by all agents."""
    hooks: list[Any] = [StopHook()]
    if max_iterations > 0:
        hooks.append(BudgetGuard(max_iterations))
    hooks.append(LoopDetector())
    hooks.append(LoggingHook(agent))
    if ctx_manager is not None:
        hooks.append(ContextHook(ctx_manager))
    return hooks
