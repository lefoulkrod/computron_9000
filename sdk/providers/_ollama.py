"""Ollama provider implementation."""

import logging
from collections.abc import Callable
from typing import Any

from ollama import AsyncClient

from config import LLMConfig

from ._models import ChatMessage, ChatResponse, ProviderError, TokenUsage, ToolCall, ToolCallFunction

logger = logging.getLogger(__name__)


class OllamaProvider:
    """LLM provider backed by an Ollama server."""

    def __init__(self, host: str | None = None) -> None:
        self._client = AsyncClient(host=host)

    @classmethod
    def from_config(cls, llm_config: LLMConfig) -> "OllamaProvider":
        """Construct from application config."""
        return cls(host=llm_config.host)

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[Callable[..., Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool = False,
    ) -> ChatResponse:
        """Send a chat request via Ollama and normalize the response."""
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": think,
        }
        if tools:
            kwargs["tools"] = tools
        if options:
            kwargs["options"] = options

        try:
            raw = await self._client.chat(**kwargs)
        except Exception as exc:
            raise _wrap_ollama_error(exc) from exc
        return _normalize_response(raw)

    async def list_models(self) -> list[str]:
        """Return available model names from the Ollama server."""
        response = await self._client.list()
        return [m.model for m in response.models if m.model is not None]


def _wrap_ollama_error(exc: Exception) -> ProviderError:
    """Convert an Ollama client exception into a ProviderError."""
    from httpx import HTTPStatusError

    status_code = None
    if isinstance(exc, HTTPStatusError):
        status_code = exc.response.status_code
    return ProviderError(
        str(exc), retryable=True, status_code=status_code, cause=exc,
    )


def _normalize_tool_calls(
    raw_tool_calls: list[Any] | None,
) -> list[ToolCall] | None:
    """Convert Ollama tool calls to normalized ToolCall objects."""
    if not raw_tool_calls:
        return None
    result: list[ToolCall] = []
    for tc in raw_tool_calls:
        func = getattr(tc, "function", None)
        if func is None:
            continue
        result.append(ToolCall(
            function=ToolCallFunction(
                name=getattr(func, "name", ""),
                arguments=getattr(func, "arguments", {}),
            ),
        ))
    return result or None


def _normalize_response(raw: Any) -> ChatResponse:
    """Convert an Ollama ChatResponse to our normalized ChatResponse."""
    msg = raw.message
    return ChatResponse(
        message=ChatMessage(
            content=getattr(msg, "content", None),
            thinking=getattr(msg, "thinking", None),
            tool_calls=_normalize_tool_calls(getattr(msg, "tool_calls", None)),
        ),
        usage=TokenUsage(
            prompt_tokens=getattr(raw, "prompt_eval_count", 0) or 0,
            completion_tokens=getattr(raw, "eval_count", 0) or 0,
        ),
        done_reason=getattr(raw, "done_reason", None),
        raw=raw,
    )
