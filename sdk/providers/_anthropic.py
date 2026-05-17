"""Anthropic provider implementation."""

import json
import logging
import time
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from typing import Any

from ._base import BaseAPIProvider
from ._models import ChatDelta, ChatMessage, ChatResponse, ModelInfo, ProviderError, TokenUsage, ToolCall, ToolCallFunction
from sdk.tools import callable_to_json_schema

logger = logging.getLogger(__name__)

_MODEL_CACHE_TTL = 300.0  # 5 minutes

# Anthropic stop reason → normalized done_reason
_STOP_REASON_MAP: dict[str, str] = {
    "end_turn": "stop",
    "tool_use": "tool_calls",
    "max_tokens": "length",
    "stop_sequence": "stop",
}


class AnthropicProvider(BaseAPIProvider):
    """LLM provider backed by the Anthropic Messages API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        proxy_socket: Path | None = None,
    ) -> None:
        super().__init__(api_key, base_url)
        import anthropic

        if proxy_socket is not None:
            # Route all SDK traffic through the llm_proxy broker's UDS.
            # The Anthropic SDK adds /v1/messages paths relative to base_url;
            # using "http://localhost" means it sends to http://localhost/v1/...
            # which the proxy receives and forwards to the real upstream.
            import httpx
            transport = httpx.AsyncHTTPTransport(uds=str(proxy_socket))
            http_client = httpx.AsyncClient(transport=transport)
            self._client = anthropic.AsyncAnthropic(
                http_client=http_client,
                base_url="http://localhost",
                api_key="proxy",
            )
        else:
            kwargs: dict[str, Any] = {}
            if api_key:
                kwargs["api_key"] = api_key
            if base_url:
                kwargs["base_url"] = base_url
            self._client = anthropic.AsyncAnthropic(**kwargs)

        self._model_cache: list[ModelInfo] | None = None
        self._model_cache_at: float = 0.0

    def _build_kwargs(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[Callable[..., Any]] | None,
        options: dict[str, Any] | None,
        think: bool,
    ) -> dict[str, Any]:
        """Build kwargs dict for the Anthropic messages API."""
        opts = options or {}
        system_prompt, converted = _convert_messages(messages)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": converted,
            "max_tokens": opts.get("num_predict") or opts.get("max_tokens") or 16384,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if opts.get("temperature") is not None:
            kwargs["temperature"] = opts["temperature"]
        if opts.get("top_k") is not None:
            kwargs["top_k"] = opts["top_k"]
        if opts.get("top_p") is not None:
            kwargs["top_p"] = opts["top_p"]

        if tools:
            kwargs["tools"] = _convert_tools(tools)

        if think:
            kwargs["temperature"] = 1
            max_tok = kwargs["max_tokens"]
            thinking_budget = opts.get("thinking_budget", "standard")
            budget_map = {"minimal": 1024, "standard": max_tok // 2, "extended": max_tok}
            budget = budget_map.get(thinking_budget, max_tok // 2)
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": max(1024, budget)}

        return kwargs

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[Callable[..., Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool = False,
    ) -> ChatResponse:
        """Send a chat request via Anthropic and normalize the response."""
        kwargs = self._build_kwargs(model, messages, tools, options, think)

        try:
            async with self._client.messages.stream(**kwargs) as stream:
                response = await stream.get_final_message()
        except Exception as exc:
            raise _wrap_error(exc) from exc
        return _normalize_response(response)

    async def chat_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[Callable[..., Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool = False,
    ) -> AsyncGenerator[ChatDelta | ChatResponse, None]:
        """Stream token deltas followed by a final ChatResponse."""
        kwargs = self._build_kwargs(model, messages, tools, options, think)

        try:
            async with self._client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    if event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            yield ChatDelta(content=event.delta.text)
                        elif event.delta.type == "thinking_delta":
                            yield ChatDelta(thinking=event.delta.thinking)
                response = await stream.get_final_message()
        except Exception as exc:
            raise _wrap_error(exc) from exc
        yield _normalize_response(response)

    async def list_models(self) -> list[ModelInfo]:
        """Return available Anthropic models with metadata, cached for 5 minutes."""
        now = time.monotonic()
        if self._model_cache is not None and now - self._model_cache_at < _MODEL_CACHE_TTL:
            return self._model_cache
        try:
            response = await self._client.models.list(limit=100)
            results: list[ModelInfo] = []
            for m in response.data:
                results.append(ModelInfo(
                    name=m.id,
                    context_window=getattr(m, "max_input_tokens", None),
                    max_output_tokens=getattr(m, "max_tokens", None),
                    supports_images=_supports_images(m.id),
                    supports_thinking=_supports_thinking(m.id),
                ))
            self._model_cache = results
            self._model_cache_at = now
            return self._model_cache
        except Exception as exc:
            raise _wrap_error(exc) from exc

    def invalidate_model_cache(self) -> None:
        """Clear the cached model list so the next call re-fetches."""
        self._model_cache = None
        self._model_cache_at = 0.0


def _supports_images(model_id: str) -> bool:
    """All Claude 3+ models support image input."""
    return any(
        prefix in model_id
        for prefix in ("claude-3", "claude-sonnet-4", "claude-opus-4", "claude-haiku-4")
    )


def _supports_thinking(model_id: str) -> bool:
    """Claude 3.7 Sonnet and Claude 4+ support extended thinking."""
    return any(
        prefix in model_id
        for prefix in ("claude-3-7-sonnet", "claude-sonnet-4", "claude-opus-4")
    )


def _convert_messages(
    messages: list[dict[str, Any]],
) -> tuple[str | None, list[dict[str, Any]]]:
    """Convert internal message format to Anthropic's format.

    Returns:
        Tuple of (system_prompt, messages).
    """
    system_prompt: str | None = None
    converted: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "")

        if role == "system":
            system_prompt = msg.get("content", "")
            continue

        if role == "assistant":
            content_blocks: list[dict[str, Any]] = []
            text = msg.get("content")
            if text:
                content_blocks.append({"type": "text", "text": text})
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    func = tc.get("function", {})
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": func.get("name", ""),
                        "input": func.get("arguments", {}),
                    })
            if content_blocks:
                converted.append({"role": "assistant", "content": content_blocks})
            continue

        if role == "tool":
            converted.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id", ""),
                    "content": msg.get("content", ""),
                }],
            })
            continue

        # user messages
        images = msg.get("images")
        if images:
            content_blocks: list[dict[str, Any]] = []
            text = msg.get("content")
            if text:
                content_blocks.append({"type": "text", "text": text})
            for img in images:
                content_blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img.get("media_type", "image/png"),
                        "data": img["data"],
                    },
                })
            converted.append({"role": "user", "content": content_blocks})
        else:
            converted.append({"role": "user", "content": msg.get("content", "")})

    return system_prompt, converted


def _convert_tools(tools: list[Callable[..., Any]]) -> list[dict[str, Any]]:
    """Convert Python callables to Anthropic's tool format."""
    result: list[dict[str, Any]] = []
    for func in tools:
        schema = callable_to_json_schema(func)
        fn = schema.get("function", {})
        result.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {}),
        })
    return result


_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504, 529}


def _extract_api_message(exc: Exception) -> str:
    """Pull the human-readable message out of an Anthropic API error."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        # Direct shape: body = {message: "..."}
        if body.get("message"):
            return body["message"]
        # Nested shape: body = {error: {type, message}}
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            msg = err["message"]
            err_type = err.get("type", "")
            if err_type:
                return f"{err_type}: {msg}"
            return msg
    return str(exc)


def _wrap_error(exc: Exception) -> ProviderError:
    """Convert an Anthropic SDK exception into a ProviderError."""
    import anthropic

    if isinstance(exc, anthropic.APIStatusError):
        retryable = exc.status_code in _RETRYABLE_STATUS_CODES
        msg = _extract_api_message(exc)
        return ProviderError(
            msg,
            retryable=retryable,
            status_code=exc.status_code,
            cause=exc,
        )
    if isinstance(exc, anthropic.APIConnectionError):
        return ProviderError(str(exc), retryable=True, cause=exc)
    return ProviderError(str(exc), retryable=False, cause=exc)


def _normalize_response(raw: Any) -> ChatResponse:
    """Convert an Anthropic Message to our normalized ChatResponse."""
    content_parts: list[str] = []
    thinking_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    for block in raw.content:
        if block.type == "text":
            content_parts.append(block.text)
        elif block.type == "thinking":
            thinking_parts.append(block.thinking)
        elif block.type == "tool_use":
            args = block.input
            if isinstance(args, str):
                args = json.loads(args)
            tool_calls.append(ToolCall(
                id=block.id,
                function=ToolCallFunction(
                    name=block.name,
                    arguments=args,
                ),
            ))

    return ChatResponse(
        message=ChatMessage(
            content="\n".join(content_parts) if content_parts else None,
            thinking="\n".join(thinking_parts) if thinking_parts else None,
            tool_calls=tool_calls or None,
        ),
        usage=TokenUsage(
            prompt_tokens=raw.usage.input_tokens,
            completion_tokens=raw.usage.output_tokens,
        ),
        done_reason=_STOP_REASON_MAP.get(raw.stop_reason, raw.stop_reason),
        raw=raw,
    )
