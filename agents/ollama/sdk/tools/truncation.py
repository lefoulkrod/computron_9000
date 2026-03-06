"""Helpers for truncating large tool call arguments in message history.

The ``truncate_args`` decorator lives in ``tools._truncation`` (dependency-free)
so tool modules can import it without circular imports.  This module re-exports
the decorator and provides the ``truncate_tool_call_args`` helper used by the
tool loop.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from typing import Any

from tools._truncation import TRUNCATE_ATTR, truncate_args

logger = logging.getLogger(__name__)


def truncate_tool_call_args(
    tool_calls: list[Any],
    tools: list[Callable[..., Any]],
) -> list[Any]:
    """Return a copy of *tool_calls* with large arguments replaced by placeholders.

    Looks up each called function in *tools* and checks for the ``_truncate_args``
    attribute set by the ``@truncate_args`` decorator.  Only arguments that exceed
    their declared threshold are modified; everything else passes through unchanged.

    Args:
        tool_calls: The ``tool_calls`` list from an assistant ``ChatResponse``.
        tools: The list of tool functions available to the agent.

    Returns:
        A (potentially shallow-copied) list of tool calls with large args replaced.
    """
    # Build a lookup from function name -> truncation thresholds.
    truncation_map: dict[str, dict[str, int]] = {}
    for tool in tools:
        thresholds = getattr(tool, TRUNCATE_ATTR, None)
        if thresholds:
            name = getattr(tool, "__name__", None)
            if name:
                truncation_map[name] = thresholds

    if not truncation_map:
        return tool_calls

    result = []
    for tc in tool_calls:
        func = getattr(tc, "function", None)
        if not func:
            result.append(tc)
            continue

        name = getattr(func, "name", None)
        thresholds = truncation_map.get(name) if name else None
        if not thresholds:
            result.append(tc)
            continue

        args = getattr(func, "arguments", None)
        if not args or not isinstance(args, dict):
            result.append(tc)
            continue

        # Deep-copy only when we actually need to mutate.
        new_args = copy.copy(args)
        mutated = False
        for param_name, max_chars in thresholds.items():
            val = new_args.get(param_name)
            if not isinstance(val, str):
                continue
            if max_chars == 0 or len(val) > max_chars:
                original_len = len(val)
                if max_chars > 0:
                    new_args[param_name] = (
                        f"{val[:max_chars]}\n[...truncated, {original_len:,} chars total]"
                    )
                else:
                    new_args[param_name] = (
                        f"[CONTEXT SAVED: {original_len:,} chars omitted from"
                        f" history. The full content was already delivered and"
                        f" the tool executed — check the tool result below.]"
                    )
                mutated = True

        if mutated:
            # Build a new tool call with the truncated arguments.
            tc_copy = copy.copy(tc)
            func_copy = copy.copy(func)
            func_copy.arguments = new_args
            tc_copy.function = func_copy
            result.append(tc_copy)
        else:
            result.append(tc)

    return result


__all__ = ["truncate_args", "truncate_tool_call_args"]
