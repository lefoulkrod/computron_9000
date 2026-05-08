"""OpenAI Responses API provider implementation.

Uses the newer /v1/responses endpoint which supports models like o3, o4-mini,
and gpt-5-codex that are not available via /v1/chat/completions.
"""

import json
import logging
import time
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from typing import Any

from config import LLMConfig

from ._base import BaseAPIProvider
from ._models import ChatDelta, ChatMessage, ChatResponse, ProviderError, TokenUsage, ToolCall, ToolCallFunction
from ._tool_schema import callable_to_json_schema

logger = logging.getLogger(__name__)

_MODEL_CACHE_TTL = 300.0  # 5 minutes

_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}

# Response status → normalized done_reason
_DONE_REASON_MAP: dict[str, str] = {
    "completed": "stop",
    "incomplete": "length",
    "failed": "stop",
}


class OpenAIResponsesProvider(BaseAPIProvider):
    """LLM provider backed by the OpenAI Responses API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        proxy_socket: Path | None = None,
    ) -> None:
        super().__init__(api_key, base_url)
        import openai

        if proxy_socket is not None:
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
            kwargs["api_key"] = api_key or "not-required"
            self._client = openai.AsyncOpenAI(**kwargs)

        self._model_cache: list[str] | None = None
        self._model_cache_at: float = 0.0

    @classmethod
    def from_config(cls, llm_config: LLMConfig) -> "OpenAIResponsesProvider":
        """Construct from application config."""
        return cls(api_key=llm_config.api_key, base_url=llm_config.base_url)

    def _build_kwargs(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[Callable[..., Any]] | None,
        options: dict[str, Any] | None,
        think: bool,
    ) -> dict[str, Any]:
        """Build kwargs dict for the OpenAI Responses API."""
        opts = options or {}
        instructions, input_items = _convert_messages(messages)

        kwargs: dict[str, Any] = {
            "model": model,
            "input": input_items,
            "store": False,
        }
        if instructions:
            kwargs["instructions"] = instructions
        max_tokens = opts.get("num_predict") or opts.get("max_tokens")
        if max_tokens:
            kwargs["max_output_tokens"] = max_tokens
        if opts.get("temperature") is not None:
            kwargs["temperature"] = opts["temperature"]
        if opts.get("top_p") is not None:
            kwargs["top_p"] = opts["top_p"]
        if tools:
            kwargs["tools"] = _convert_tools(tools)
        if think:
            effort = opts.get("reasoning_effort", "medium")
            summary = opts.get("reasoning_summary", "auto")
            kwargs["reasoning"] = {"effort": effort, "summary": summary}
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
        """Send a request via the Responses API and return a normalized response."""
        kwargs = self._build_kwargs(model, messages, tools, options, think)
        try:
            response = await self._client.responses.create(**kwargs)
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

        content_parts: list[str] = []
        thinking_parts: list[str] = []
        # tool_call accumulator: output_index → {id, call_id, name, arguments}
        tc_accum: dict[int, dict[str, str]] = {}
        final_response: Any = None

        try:
            stream = await self._client.responses.create(**kwargs)
            async for event in stream:
                if event.type == "response.output_text.delta":
                    content_parts.append(event.delta)
                    yield ChatDelta(content=event.delta)

                elif event.type == "response.reasoning_summary_text.delta":
                    thinking_parts.append(event.delta)
                    yield ChatDelta(thinking=event.delta)

                elif event.type == "response.function_call_arguments.delta":
                    idx = event.output_index
                    if idx not in tc_accum:
                        tc_accum[idx] = {"id": "", "call_id": "", "name": "", "arguments": ""}
                    tc_accum[idx]["arguments"] += event.delta

                elif event.type == "response.output_item.added":
                    item = event.item
                    if getattr(item, "type", None) == "function_call":
                        idx = event.output_index
                        tc_accum[idx] = {
                            "id": getattr(item, "id", "") or "",
                            "call_id": getattr(item, "call_id", "") or "",
                            "name": getattr(item, "name", "") or "",
                            "arguments": "",
                        }

                elif event.type == "response.completed":
                    final_response = event.response

        except Exception as exc:
            raise _wrap_error(exc) from exc

        tool_calls = _build_tool_calls(tc_accum) if tc_accum else None

        usage = getattr(final_response, "usage", None)
        status = getattr(final_response, "status", None)

        yield ChatResponse(
            message=ChatMessage(
                content="".join(content_parts) or None,
                thinking="".join(thinking_parts) or None,
                tool_calls=tool_calls,
            ),
            usage=TokenUsage(
                prompt_tokens=getattr(usage, "input_tokens", 0) or 0,
                completion_tokens=getattr(usage, "output_tokens", 0) or 0,
            ),
            done_reason=_DONE_REASON_MAP.get(status or "", status),
        )

    async def list_models(self) -> list[str]:
        """Return available model names, with a 5-minute in-memory cache."""
        now = time.monotonic()
        if self._model_cache is not None and now - self._model_cache_at < _MODEL_CACHE_TTL:
            return self._model_cache
        try:
            response = await self._client.models.list()
            self._model_cache = [m.id for m in response.data]
            self._model_cache_at = now
            return self._model_cache
        except Exception as exc:
            raise _wrap_error(exc) from exc

    def invalidate_model_cache(self) -> None:
        """Clear the cached model list so the next call re-fetches."""
        self._model_cache = None
        self._model_cache_at = 0.0


# ---------------------------------------------------------------------------
# Message conversion
# ---------------------------------------------------------------------------


def _convert_messages(
    messages: list[dict[str, Any]],
) -> tuple[str | None, list[dict[str, Any]]]:
    """Convert internal message format to Responses API input items.

    Returns:
        Tuple of (instructions, input_items).
    """
    instructions: str | None = None
    items: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "")

        if role == "system":
            instructions = msg.get("content", "")
            continue

        if role == "user":
            content = msg.get("content", "")
            images = msg.get("images")
            if images:
                content_parts: list[dict[str, Any]] = []
                if content:
                    content_parts.append({"type": "input_text", "text": content})
                for img in images:
                    media_type = img.get("media_type", "image/png")
                    content_parts.append({
                        "type": "input_image",
                        "image_url": f"data:{media_type};base64,{img['data']}",
                    })
                items.append({"role": "user", "content": content_parts})
            else:
                items.append({"role": "user", "content": content})
            continue

        if role == "assistant":
            content = msg.get("content")
            tool_calls = msg.get("tool_calls")

            # Emit text as an output message item
            if content:
                items.append({
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": content, "annotations": []}],
                })

            # Emit tool calls as function_call items
            if tool_calls:
                for tc in tool_calls:
                    func = tc.get("function", {})
                    args = func.get("arguments", {})
                    call_id = tc.get("id", "")
                    # The Responses API requires item IDs starting with "fc_"
                    # and call_ids starting with "call_". Our ToolCall model
                    # stores only the call_id, so derive an item ID from it.
                    if call_id.startswith("call_"):
                        item_id = "fc_" + call_id[5:]
                    else:
                        item_id = call_id
                    items.append({
                        "type": "function_call",
                        "id": item_id,
                        "call_id": call_id,
                        "name": func.get("name", ""),
                        "arguments": json.dumps(args) if isinstance(args, dict) else args,
                    })
            continue

        if role == "tool":
            content = msg.get("content", "")
            if isinstance(content, dict):
                content = json.dumps(content)
            items.append({
                "type": "function_call_output",
                "call_id": msg.get("tool_call_id", ""),
                "output": content,
            })
            continue

    return instructions, items


# ---------------------------------------------------------------------------
# Tool conversion
# ---------------------------------------------------------------------------


def _convert_tools(tools: list[Callable[..., Any]]) -> list[dict[str, Any]]:
    """Convert Python callables to Responses API tool format."""
    result: list[dict[str, Any]] = []
    for func in tools:
        schema = callable_to_json_schema(func)
        fn = schema.get("function", {})
        result.append({
            "type": "function",
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters", {}),
        })
    return result


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
            id=tc["call_id"] or tc["id"] or None,
            function=ToolCallFunction(name=tc["name"], arguments=args),
        ))
    return result or None


# ---------------------------------------------------------------------------
# Response normalization
# ---------------------------------------------------------------------------


def _normalize_response(raw: Any) -> ChatResponse:
    """Convert a Responses API Response to our normalized ChatResponse."""
    content_parts: list[str] = []
    thinking_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    for item in raw.output:
        if item.type == "message":
            for block in item.content:
                if block.type == "output_text":
                    content_parts.append(block.text)
        elif item.type == "function_call":
            args: dict[str, Any] = {}
            if item.arguments:
                try:
                    args = json.loads(item.arguments)
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append(ToolCall(
                id=item.call_id,
                function=ToolCallFunction(name=item.name, arguments=args),
            ))
        elif item.type == "reasoning":
            for summary in getattr(item, "summary", []) or []:
                if getattr(summary, "type", None) == "summary_text":
                    thinking_parts.append(summary.text)

    usage = raw.usage
    done_reason = _DONE_REASON_MAP.get(raw.status or "", raw.status)
    # If we got tool calls, signal that as the done_reason
    if tool_calls and done_reason == "stop":
        done_reason = "tool_calls"

    return ChatResponse(
        message=ChatMessage(
            content="\n".join(content_parts) if content_parts else None,
            thinking="\n".join(thinking_parts) if thinking_parts else None,
            tool_calls=tool_calls or None,
        ),
        usage=TokenUsage(
            prompt_tokens=getattr(usage, "input_tokens", 0) or 0,
            completion_tokens=getattr(usage, "output_tokens", 0) or 0,
        ),
        done_reason=done_reason,
        raw=raw,
    )


# ---------------------------------------------------------------------------
# Error wrapping
# ---------------------------------------------------------------------------


def _extract_api_message(exc: Exception) -> str:
    """Pull the human-readable message out of an OpenAI API error."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        if body.get("message"):
            return body["message"]
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
