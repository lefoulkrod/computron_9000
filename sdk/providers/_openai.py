"""OpenAI provider implementation."""

import json
import logging
import time
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from typing import Any

from ._base import BaseAPIProvider
from ._models import ChatDelta, ChatMessage, ChatResponse, LLMConfig, ModelInfo, ProviderError, TokenUsage, ToolCall, ToolCallFunction
from sdk.tools import callable_to_json_schema

logger = logging.getLogger(__name__)

_MODEL_CACHE_TTL = 300.0  # 5 minutes

# Finish reason → normalized done_reason
_DONE_REASON_MAP: dict[str, str] = {
    "stop": "stop",
    "length": "length",
    "tool_calls": "tool_calls",
    "content_filter": "stop",
}

_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class OpenAIProvider(BaseAPIProvider):
    """LLM provider backed by the OpenAI API or any OpenAI-compatible endpoint."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        proxy_socket: Path | None = None,
    ) -> None:
        super().__init__(api_key, base_url)
        # Lazy import — the openai package is an optional heavy dep.
        import openai

        if proxy_socket is not None:
            # Route all SDK traffic through the llm_proxy broker's UDS.
            # The broker injects the real API key; we pass a placeholder so
            # the SDK doesn't complain about a missing key.
            import httpx
            transport = httpx.AsyncHTTPTransport(uds=str(proxy_socket))
            http_client = httpx.AsyncClient(transport=transport)
            self._client = openai.AsyncOpenAI(
                http_client=http_client,
                base_url="http://localhost/v1",
                api_key="proxy",
            )
        else:
            kwargs: dict[str, Any] = {}
            if base_url:
                kwargs["base_url"] = base_url
            # Many OpenAI-compatible servers require a non-empty api_key even when
            # auth is disabled; use a placeholder so the SDK doesn't complain.
            kwargs["api_key"] = api_key or "not-required"
            self._client = openai.AsyncOpenAI(**kwargs)

        self._model_cache: list[ModelInfo] | None = None
        self._model_cache_at: float = 0.0

    @classmethod
    def from_config(cls, llm_config: LLMConfig) -> "OpenAIProvider":
        """Construct from a direct-provider config (no API key — that path is brokered)."""
        return cls(base_url=llm_config.base_url)

    def _build_kwargs(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[Callable[..., Any]] | None,
        options: dict[str, Any] | None,
        think: bool = False,
    ) -> dict[str, Any]:
        """Build kwargs dict for the OpenAI chat completions API."""
        opts = options or {}
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": _convert_messages_for_openai(messages),
        }
        max_tokens = opts.get("num_predict") or opts.get("max_tokens")
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if opts.get("temperature") is not None:
            kwargs["temperature"] = opts["temperature"]
        if opts.get("top_p") is not None:
            kwargs["top_p"] = opts["top_p"]
        if tools:
            kwargs["tools"] = _convert_tools(tools)
            kwargs["tool_choice"] = "auto"
        if think:
            effort = opts.get("reasoning_effort", "medium")
            kwargs["reasoning_effort"] = effort
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
        """Send a chat request via OpenAI and return a normalized response."""
        kwargs = self._build_kwargs(model, messages, tools, options, think)
        try:
            response = await self._client.chat.completions.create(**kwargs, stream=False)
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
        kwargs["stream"] = True
        # Request usage in the last chunk; some compat servers silently ignore this.
        kwargs["stream_options"] = {"include_usage": True}

        content_parts: list[str] = []
        thinking_parts: list[str] = []
        # tool_call accumulator: index → {id, name, arguments_str}
        tc_accum: dict[int, dict[str, str]] = {}
        usage_data: Any = None
        finish_reason: str | None = None

        try:
            stream = await self._client.chat.completions.create(**kwargs)
            async for chunk in stream:
                # Some providers send usage on a dedicated empty-choices chunk;
                # others attach it to the final chunk alongside finish_reason.
                if chunk.usage:
                    usage_data = chunk.usage
                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                if choice.finish_reason:
                    finish_reason = choice.finish_reason

                delta = choice.delta
                chunk_content = delta.content or None
                chunk_thinking = getattr(delta, "reasoning", None) or getattr(delta, "reasoning_content", None) or None

                if chunk_content:
                    content_parts.append(chunk_content)
                if chunk_thinking:
                    thinking_parts.append(chunk_thinking)
                if chunk_content or chunk_thinking:
                    yield ChatDelta(content=chunk_content, thinking=chunk_thinking)

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tc_accum:
                            tc_accum[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc_delta.id:
                            tc_accum[idx]["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                tc_accum[idx]["name"] += tc_delta.function.name
                            if tc_delta.function.arguments:
                                tc_accum[idx]["arguments"] += tc_delta.function.arguments
        except Exception as exc:
            raise _wrap_error(exc) from exc

        tool_calls = _build_tool_calls(tc_accum) if tc_accum else None

        yield ChatResponse(
            message=ChatMessage(
                content="".join(content_parts) or None,
                thinking="".join(thinking_parts) or None,
                tool_calls=tool_calls,
            ),
            usage=_extract_usage(usage_data),
            done_reason=_DONE_REASON_MAP.get(finish_reason or "", finish_reason),
        )

    async def list_models(self) -> list[ModelInfo]:
        """Return available models with metadata, cached for 5 minutes.

        Attempts to parse rich fields (context_length, input_modalities) that
        OpenRouter and some compatible endpoints include in model objects.
        Falls back to minimal ModelInfo for endpoints that only return id.
        """
        now = time.monotonic()
        if self._model_cache is not None and now - self._model_cache_at < _MODEL_CACHE_TTL:
            return self._model_cache
        try:
            response = await self._client.models.list()
            results: list[ModelInfo] = []
            for m in response.data:
                results.append(_parse_model_object(m))
            self._model_cache = results
            self._model_cache_at = now
            return self._model_cache
        except Exception as exc:
            raise _wrap_error(exc) from exc

    def invalidate_model_cache(self) -> None:
        """Clear the cached model list so the next call re-fetches."""
        self._model_cache = None
        self._model_cache_at = 0.0


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Model metadata parsing
# ---------------------------------------------------------------------------


def _parse_model_object(m: Any) -> ModelInfo:
    """Extract ModelInfo from an OpenAI SDK model object.

    OpenRouter includes extra fields (context_length, architecture, etc.)
    that the SDK may preserve as extra attributes. Parse them when present.
    """
    ctx: int | None = getattr(m, "context_length", None)
    max_out: int | None = None
    images = False

    # OpenRouter: top_provider.max_completion_tokens
    top_provider = getattr(m, "top_provider", None)
    if top_provider is not None:
        max_out = getattr(top_provider, "max_completion_tokens", None)
        if isinstance(top_provider, dict):
            max_out = top_provider.get("max_completion_tokens")

    # OpenRouter: architecture.input_modalities
    arch = getattr(m, "architecture", None)
    if arch is not None:
        modalities = getattr(arch, "input_modalities", None)
        if isinstance(arch, dict):
            modalities = arch.get("input_modalities")
        if isinstance(modalities, list):
            images = "image" in modalities

    # OpenRouter: supported_parameters contains "reasoning" for thinking models
    thinking = False
    supported_params = getattr(m, "supported_parameters", None)
    if isinstance(supported_params, list):
        thinking = "reasoning" in supported_params

    return ModelInfo(
        name=m.id,
        context_window=ctx if isinstance(ctx, int) else None,
        max_output_tokens=max_out if isinstance(max_out, int) else None,
        supports_images=images,
        supports_thinking=thinking,
    )


# ---------------------------------------------------------------------------
# Message conversion
# ---------------------------------------------------------------------------


def _convert_messages_for_openai(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert internal message format to OpenAI's expected format.

    The internal format stores tool_call arguments as dicts; OpenAI expects
    them serialized as JSON strings.  Tool calls also need ``type: "function"``
    added.  Images are converted to content arrays with image_url blocks.
    """
    converted = []
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            openai_tcs = []
            for tc in msg["tool_calls"]:
                func = tc.get("function", {})
                args = func.get("arguments", {})
                openai_tcs.append({
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": func.get("name", ""),
                        "arguments": json.dumps(args) if isinstance(args, dict) else args,
                    },
                })
            converted.append({
                "role": "assistant",
                "content": msg.get("content"),
                "tool_calls": openai_tcs,
            })
        elif msg.get("images"):
            content_parts: list[dict[str, Any]] = []
            text = msg.get("content")
            if text:
                content_parts.append({"type": "text", "text": text})
            for img in msg["images"]:
                media_type = img.get("media_type", "image/png")
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{img['data']}"},
                })
            converted.append({"role": msg.get("role", "user"), "content": content_parts})
        else:
            converted.append(msg)
    return converted


# ---------------------------------------------------------------------------
# Tool conversion
# ---------------------------------------------------------------------------


def _convert_tools(tools: list[Callable[..., Any]]) -> list[dict[str, Any]]:
    """Convert Python callables to OpenAI's tool format."""
    # callable_to_json_schema already returns the OpenAI tool schema shape
    # {type: "function", function: {name, description, parameters}}.
    return [callable_to_json_schema(func) for func in tools]


def _build_tool_calls(tc_accum: dict[int, dict[str, str]]) -> list[ToolCall] | None:
    """Convert accumulated streaming tool call fragments to ToolCall objects."""
    result = []
    for tc in tc_accum.values():
        args: dict[str, Any] = {}
        if tc["arguments"]:
            try:
                args = json.loads(tc["arguments"])
            except json.JSONDecodeError:
                args = {}
        result.append(ToolCall(
            id=tc["id"] or None,
            function=ToolCallFunction(name=tc["name"], arguments=args),
        ))
    return result or None


# ---------------------------------------------------------------------------
# Response normalization
# ---------------------------------------------------------------------------


def _extract_usage(usage: Any) -> TokenUsage:
    """Extract token counts including cache metrics from an OpenAI usage object.

    OpenAI includes cached prompt tokens in usage.prompt_tokens_details.cached_tokens.
    OpenRouter may include similar fields. Gracefully degrade when absent.
    """
    if usage is None:
        return TokenUsage()

    prompt = getattr(usage, "prompt_tokens", 0) or 0
    completion = getattr(usage, "completion_tokens", 0) or 0

    # OpenAI / OpenRouter: usage.prompt_tokens_details.cached_tokens
    cache_read = 0
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cache_read = getattr(details, "cached_tokens", 0) or 0

    result = TokenUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        cache_read_tokens=cache_read,
    )
    if cache_read:
        logger.debug("cache tokens: read=%d (prompt=%d, completion=%d)", cache_read, prompt, completion)
    return result


def _normalize_response(raw: Any) -> ChatResponse:
    """Convert an OpenAI ChatCompletion to our normalized ChatResponse."""
    choice = raw.choices[0]
    msg = choice.message

    tool_calls: list[ToolCall] | None = None
    if msg.tool_calls:
        tool_calls = []
        for tc in msg.tool_calls:
            args: dict[str, Any] = {}
            if tc.function.arguments:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append(ToolCall(
                id=tc.id,
                function=ToolCallFunction(name=tc.function.name, arguments=args),
            ))

    thinking = getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None) or None

    return ChatResponse(
        message=ChatMessage(
            content=msg.content,
            thinking=thinking,
            tool_calls=tool_calls or None,
        ),
        usage=_extract_usage(raw.usage),
        done_reason=_DONE_REASON_MAP.get(choice.finish_reason or "", choice.finish_reason),
        raw=raw,
    )


# ---------------------------------------------------------------------------
# Error wrapping
# ---------------------------------------------------------------------------


def _extract_api_message(exc: Exception) -> str:
    """Pull the human-readable message out of an OpenAI API error."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        # Direct shape: body = {message: "..."}  (proxy broker path)
        if body.get("message"):
            return body["message"]
        # Nested shape: body = {error: {message: "..."}}  (direct API path)
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return err["message"]
    return str(exc)


def _wrap_error(exc: Exception) -> ProviderError:
    """Convert an OpenAI SDK exception into a ProviderError."""
    import openai

    if isinstance(exc, openai.APIStatusError):
        retryable = exc.status_code in _RETRYABLE_STATUS_CODES
        msg = _extract_api_message(exc)
        return ProviderError(msg, retryable=retryable, status_code=exc.status_code, cause=exc)
    if isinstance(exc, openai.APIConnectionError):
        return ProviderError(str(exc), retryable=True, cause=exc)
    return ProviderError(str(exc), retryable=False, cause=exc)
