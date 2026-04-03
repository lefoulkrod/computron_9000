"""Hook that replaces oversized tool results with an actionable error."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Approximate characters per token for converting num_ctx to a char limit.
_CHARS_PER_TOKEN = 4


class ToolResultCapHook:
    """Discard tool results that exceed the model's context window.

    Constructed with ``num_ctx`` (the context window size in tokens).
    If a tool result's character count exceeds ``num_ctx * _CHARS_PER_TOKEN``,
    it is replaced with a short error message so the agent can retry with a
    more targeted request.
    """

    def __init__(self, num_ctx: int) -> None:
        self._max_chars = num_ctx * _CHARS_PER_TOKEN

    def after_tool(
        self, tool_name: str, tool_arguments: object, tool_result: str,
    ) -> str:
        """Replace the result with an error if it exceeds the context window."""
        result_len = len(tool_result) if isinstance(tool_result, str) else 0
        if result_len <= self._max_chars:
            return tool_result
        logger.warning(
            "Tool '%s' result too large (%s chars, limit %s), replacing with error",
            tool_name, f"{result_len:,}", f"{self._max_chars:,}",
        )
        return (
            f"Error: tool result too large ({result_len:,} characters). "
            f"The output exceeded the context window limit of "
            f"{self._max_chars:,} characters and was discarded. "
            f"Try again with a more targeted request — for example, "
            f"restrict to a specific file or subdirectory, use a narrower "
            f"pattern, or limit the output."
        )
