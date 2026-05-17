"""Token usage estimation over a conversation history.

Compaction decisions need to know how big the current outbound request
is — not how big the previous prompt was. The provider reports actual
token counts only after a call, so before-call decisions need an
estimate. This module walks the messages and any tool schemas and
converts chars to tokens at a fixed ratio.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sdk.tools import estimate_tool_tokens

# Average chars per token across English-heavy LLM tokenizers.
_CHARS_PER_TOKEN = 4

# Per-message framing overhead (role labels, separators, wire-format
# punctuation). Small enough not to matter for big histories, large enough
# to keep many-tiny-message conversations from underestimating drastically.
_PER_MESSAGE_OVERHEAD_CHARS = 16


def estimate_tokens(
    messages: list[dict[str, Any]],
    tools: list[Callable[..., Any]] | None = None,
) -> int:
    """Estimate the token cost of a chat request.

    Args:
        messages: The full conversation history that will be sent.
        tools: Callable tools that will be serialized into the request's
            tool schema block. Pass ``None`` to skip tool accounting.
    """
    tokens = sum(_message_chars(msg) for msg in messages) // _CHARS_PER_TOKEN
    if tools:
        tokens += sum(estimate_tool_tokens(t) for t in tools)
    return tokens


def _message_chars(msg: dict[str, Any]) -> int:
    chars = _PER_MESSAGE_OVERHEAD_CHARS

    content = msg.get("content")
    if isinstance(content, str):
        chars += len(content)

    thinking = msg.get("thinking")
    if isinstance(thinking, str):
        chars += len(thinking)

    tool_name = msg.get("tool_name")
    if isinstance(tool_name, str):
        chars += len(tool_name)

    tool_calls = msg.get("tool_calls")
    if tool_calls:
        for tc in tool_calls:
            chars += _tool_call_chars(tc)

    return chars


def _tool_call_chars(tc: dict[str, Any]) -> int:
    fn = tc.get("function") or {}
    chars = len(fn.get("name") or "")
    args = fn.get("arguments") or {}
    chars += len(json.dumps(args, default=str))
    return chars


