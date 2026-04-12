"""Ollama provider implementation."""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, Callable
from typing import Any

import httpx
from ollama import AsyncClient
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from config import LLMConfig

from ._models import ChatDelta, ChatMessage, ChatResponse, ProviderError, TokenUsage, ToolCall, ToolCallFunction

logger = logging.getLogger(__name__)
_console = Console(stderr=True)

# No read timeout — once streaming starts, never interrupt active generation.
# Connect timeout catches "Ollama is down"; first-token timeout is handled
# manually in chat().
_DEFAULT_TIMEOUT = httpx.Timeout(connect=10, read=None, write=10, pool=10)
_FIRST_TOKEN_TIMEOUT = 120.0


def _build_ollama_kwargs(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[Callable[..., Any]] | None,
    options: dict[str, Any] | None,
    think: bool,
) -> dict[str, Any]:
    """Build kwargs dict for the Ollama chat API."""
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "think": think,
    }
    if tools:
        kwargs["tools"] = tools
    if options:
        kwargs["options"] = options
    return kwargs


class OllamaProvider:
    """LLM provider backed by an Ollama server."""

    def __init__(self, host: str | None = None) -> None:
        self._client = AsyncClient(host=host, timeout=_DEFAULT_TIMEOUT)
        self._model_cache: list[dict[str, Any]] | None = None

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
        kwargs = _build_ollama_kwargs(model, messages, tools, options, think)

        try:
            raw = None
            t0 = time.monotonic()
            first_chunk_at: float | None = None
            chunk_count = 0
            # Streaming distributes content, thinking, and tool_calls across
            # intermediate chunks; the final chunk carries only stats.
            # Accumulate everything so the result matches stream=False.
            content_parts: list[str] = []
            thinking_parts: list[str] = []
            tool_calls: list[Any] = []
            stream = await self._client.chat(**kwargs)
            async for chunk in _first_token_guard(stream, _FIRST_TOKEN_TIMEOUT):
                if first_chunk_at is None:
                    first_chunk_at = time.monotonic()
                    _log_first_chunk(model, first_chunk_at - t0)
                chunk_count += 1
                raw = chunk
                if chunk.message.content:
                    content_parts.append(chunk.message.content)
                if getattr(chunk.message, "thinking", None):
                    thinking_parts.append(chunk.message.thinking)
                if getattr(chunk.message, "tool_calls", None):
                    tool_calls.extend(chunk.message.tool_calls)
            if raw is None:
                raise ProviderError("Ollama returned empty stream", retryable=True)
        except ProviderError:
            raise
        except Exception as exc:
            elapsed = time.monotonic() - t0
            _log_stream_error(model, elapsed, chunk_count)
            raise _wrap_ollama_error(exc) from exc

        # Stitch accumulated fields onto the final chunk before normalizing
        # so the result is identical to a stream=False response.
        raw.message.content = "".join(content_parts)
        if thinking_parts:
            raw.message.thinking = "".join(thinking_parts)
        if tool_calls:
            raw.message.tool_calls = tool_calls

        elapsed = time.monotonic() - t0
        response = _normalize_response(raw)
        _log_stream_complete(model, elapsed, chunk_count, response.usage)
        return response

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
        kwargs = _build_ollama_kwargs(model, messages, tools, options, think)

        try:
            raw = None
            t0 = time.monotonic()
            first_chunk_at: float | None = None
            chunk_count = 0
            content_parts: list[str] = []
            thinking_parts: list[str] = []
            tool_calls: list[Any] = []
            stream = await self._client.chat(**kwargs)
            async for chunk in _first_token_guard(stream, _FIRST_TOKEN_TIMEOUT):
                if first_chunk_at is None:
                    first_chunk_at = time.monotonic()
                    _log_first_chunk(model, first_chunk_at - t0)
                chunk_count += 1
                raw = chunk

                chunk_content = chunk.message.content or None
                chunk_thinking = getattr(chunk.message, "thinking", None) or None

                if chunk_content:
                    content_parts.append(chunk_content)
                if chunk_thinking:
                    thinking_parts.append(chunk_thinking)
                if getattr(chunk.message, "tool_calls", None):
                    tool_calls.extend(chunk.message.tool_calls)

                # Yield delta for non-empty content/thinking tokens
                if chunk_content or chunk_thinking:
                    yield ChatDelta(content=chunk_content, thinking=chunk_thinking)

            if raw is None:
                raise ProviderError("Ollama returned empty stream", retryable=True)
        except ProviderError:
            raise
        except Exception as exc:
            elapsed = time.monotonic() - t0
            _log_stream_error(model, elapsed, chunk_count)
            raise _wrap_ollama_error(exc) from exc

        # Stitch accumulated fields onto the final chunk before normalizing
        raw.message.content = "".join(content_parts)
        if thinking_parts:
            raw.message.thinking = "".join(thinking_parts)
        if tool_calls:
            raw.message.tool_calls = tool_calls

        elapsed = time.monotonic() - t0
        response = _normalize_response(raw)
        _log_stream_complete(model, elapsed, chunk_count, response.usage)
        yield response

    async def list_models(self) -> list[str]:
        """Return available model names from the Ollama server."""
        response = await self._client.list()
        return [m.model for m in response.models if m.model is not None]

    async def list_models_detailed(self) -> list[dict[str, Any]]:
        """Return models with metadata from the Ollama server.

        For each model, calls ``show`` to retrieve capabilities. Results
        are cached in memory — call ``invalidate_model_cache()`` to refresh.
        """
        if self._model_cache is not None:
            return self._model_cache

        response = await self._client.list()
        results: list[dict[str, Any]] = []
        for m in response.models:
            if m.model is None:
                continue
            name = m.model
            details = getattr(m, "details", None)

            # Fetch capabilities via show()
            capabilities: list[str] = []
            try:
                show_resp = await self._client.show(name)
                capabilities = list(getattr(show_resp, "capabilities", None) or [])
            except Exception:
                logger.debug("Failed to fetch capabilities for model '%s'", name)

            results.append({
                "name": name,
                "parameter_size": getattr(details, "parameter_size", None) if details else None,
                "quantization_level": getattr(details, "quantization_level", None) if details else None,
                "family": getattr(details, "family", None) if details else None,
                "capabilities": capabilities,
                "is_cloud": name.endswith(":cloud"),
            })

        self._model_cache = results
        return results

    def invalidate_model_cache(self) -> None:
        """Clear the cached model metadata so the next call re-fetches."""
        self._model_cache = None


# ---------------------------------------------------------------------------
# First-token timeout
# ---------------------------------------------------------------------------


async def _first_token_guard(stream: Any, timeout: float) -> Any:
    """Wrap an async iterator with a timeout on the first item only.

    After the first chunk arrives, remaining chunks are yielded without any
    timeout so active generation is never interrupted.
    """
    aiter = stream.__aiter__()
    try:
        first = await asyncio.wait_for(aiter.__anext__(), timeout=timeout)
    except StopAsyncIteration:
        return
    except asyncio.TimeoutError:
        raise ProviderError(
            f"No response from Ollama within {timeout:.0f}s",
            retryable=True,
        )
    yield first
    async for chunk in aiter:
        yield chunk


# ---------------------------------------------------------------------------
# Stream logging helpers
# ---------------------------------------------------------------------------


def _log_first_chunk(model: str, wait_secs: float) -> None:
    if not logger.isEnabledFor(logging.DEBUG):
        return
    text = Text()
    text.append("first chunk ", style="bold")
    text.append(f"{wait_secs:.1f}s", style="green" if wait_secs < 10 else "yellow")
    _console.print(Panel(
        text,
        title=f"[bold cyan]{model}[/bold cyan]  streaming",
        border_style="cyan",
        expand=False,
    ))


def _log_stream_complete(
    model: str, elapsed: float, chunks: int, usage: TokenUsage,
) -> None:
    if not logger.isEnabledFor(logging.DEBUG):
        return
    text = Text()
    text.append(f"{chunks}", style="bold")
    text.append(" chunks  ", style="dim")
    text.append(f"{elapsed:.1f}s", style="bold")
    text.append("  prompt=", style="dim")
    text.append(str(usage.prompt_tokens))
    text.append("  eval=", style="dim")
    text.append(str(usage.completion_tokens))
    _console.print(Panel(
        text,
        title=f"[bold cyan]{model}[/bold cyan]  stream complete",
        border_style="green",
        expand=False,
    ))


def _log_stream_error(model: str, elapsed: float, chunks_received: int) -> None:
    if chunks_received == 0:
        phase = "waiting for first chunk"
    else:
        phase = f"generating ({chunks_received} chunks received)"
    text = Text()
    text.append(f"failed while {phase} ", style="bold red")
    text.append(f"after {elapsed:.1f}s", style="red")
    _console.print(Panel(
        text,
        title=f"[bold cyan]{model}[/bold cyan]  stream error",
        border_style="red",
        expand=False,
    ))


# ---------------------------------------------------------------------------
# Error wrapping and response normalization
# ---------------------------------------------------------------------------


_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def _wrap_ollama_error(exc: Exception) -> ProviderError:
    """Convert an Ollama client exception into a ProviderError."""
    from ollama import ResponseError

    status_code = None
    retryable = True  # Default for non-HTTP errors (connection issues, etc.)
    if isinstance(exc, ResponseError):
        status_code = exc.status_code
        retryable = status_code in _RETRYABLE_STATUS_CODES
    return ProviderError(
        str(exc), retryable=retryable, status_code=status_code, cause=exc,
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
