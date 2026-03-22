"""Tool loop utilities for executing chat-based LLM interactions with tool calls."""

import asyncio
import inspect
import json
import logging
from collections.abc import AsyncGenerator, Callable
from typing import Any

from agents.types import Agent
from sdk.context import ConversationHistory
from sdk.events import AssistantResponse, ToolCallPayload, get_current_agent_name, publish_event
from sdk.providers import ChatDelta, ChatResponse, ProviderError, get_provider
from sdk.tools import _normalize_tool_result, _prepare_tool_arguments

from ._turn import StopRequestedError


class ToolLoopError(Exception):
    """Custom exception for errors in the tool loop."""


logger = logging.getLogger(__name__)


def _publish_final(content: str | None = None) -> None:
    """Emit a terminal AssistantResponse. Logs but never raises on failure."""
    try:
        publish_event(AssistantResponse(content=content, final=True))
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to publish terminal AssistantResponse event")


async def _stream_chat_with_retries(
    provider: Any,
    *,
    agent: Agent,
    messages: list[dict[str, Any]],
    tools: list[Callable[..., Any]] | None = None,
    retries: int = 5,
) -> AsyncGenerator[ChatDelta | ChatResponse, None]:
    """Yield ChatDelta tokens, then the final ChatResponse. Retries on failure.

    If a stream fails mid-way after emitting deltas, retrying would cause
    content duplication. On retry, fall back to non-streaming chat() to
    yield a single complete ChatResponse instead.
    """
    resolved_tools = tools if tools is not None else (agent.tools or [])
    attempt = 0
    total_attempts = 1 + max(0, retries)
    while attempt < total_attempts:
        try:
            if attempt == 0:
                async for chunk in provider.chat_stream(
                    model=agent.model,
                    messages=messages,
                    options=agent.options,
                    tools=resolved_tools,
                    think=agent.think,
                ):
                    yield chunk
            else:
                # Retry with non-streaming to avoid content duplication
                yield await provider.chat(
                    model=agent.model,
                    messages=messages,
                    options=agent.options,
                    tools=resolved_tools,
                    think=agent.think,
                )
            return
        except ProviderError as exc:
            attempt += 1
            if not exc.retryable:
                logger.error(
                    "provider.chat_stream failed (non-retryable): %s | model=%s",
                    exc,
                    agent.model,
                )
                raise
            delay = min(2 ** attempt, 32)
            logger.warning(
                "provider.chat_stream failed (attempt %s/%s, retryable, backoff %ds): %s | model=%s",
                attempt,
                total_attempts,
                delay,
                exc,
                agent.model,
            )
            if attempt >= total_attempts:
                raise
            await asyncio.sleep(delay)
        except Exception as exc:
            logger.error(
                "provider.chat_stream failed (unexpected): %s | model=%s",
                exc,
                agent.model,
            )
            raise
    msg = "Failed to get chat response after retries."
    raise ToolLoopError(msg)


async def _execute_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    tools: list[Callable[..., Any]],
) -> str:
    """Resolve and execute a single tool call, returning the result as a string.

    Args:
        tool_name: The name of the tool function to call.
        arguments: The arguments to pass to the tool function.
        tools: Available tool functions to match against.

    Returns:
        Plain string result for the LLM to read.
    """

    # Some models emit function names with Python call syntax, e.g.
    # "browse_page(full_page=True)" instead of "browse_page".  Strip the
    # trailing parenthesised portion and merge any kwargs into arguments.
    if tool_name and "(" in tool_name:
        base, _, rest = tool_name.partition("(")
        tool_name = base
        # Try to parse kwargs like "full_page=True" into arguments
        rest = rest.rstrip(")")
        if rest and not arguments:
            arguments = {}
            for part in rest.split(","):
                part = part.strip()
                if "=" in part:
                    k, _, v = part.partition("=")
                    # Coerce simple Python literals
                    v = v.strip()
                    if v in ("True", "true"):
                        arguments[k.strip()] = True
                    elif v in ("False", "false"):
                        arguments[k.strip()] = False
                    elif v.isdigit():
                        arguments[k.strip()] = int(v)
                    else:
                        arguments[k.strip()] = v.strip("\"'")

    try:
        publish_event(AssistantResponse(event=ToolCallPayload(type="tool_call", name=str(tool_name))))
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to publish tool_call event for tool '%s'", tool_name)

    tool_func = next(
        (t for t in tools if getattr(t, "__name__", None) == tool_name),
        None,
    )
    if not tool_func:
        logger.error("Tool '%s' not found in tools.", tool_name)
        return "Tool not found"

    try:
        validated_args = _prepare_tool_arguments(tool_func, arguments)
        if inspect.iscoroutinefunction(tool_func):
            result = await tool_func(**validated_args)
        else:
            result = tool_func(**validated_args)
        normalized = _normalize_tool_result(result)
        return str(normalized) if not isinstance(normalized, str) else normalized
    except StopRequestedError:
        raise
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        logger.exception("Argument validation failed for tool '%s'", tool_name)
        return f"Argument validation failed: {exc}"
    except Exception as exc:
        logger.exception("Error running tool '%s'", tool_name)
        return str(exc)


async def _run_tool_with_hooks(
    tool_call: Any,
    tools: list[Callable[..., Any]],
    hooks: list[Any],
) -> dict[str, Any]:
    """Execute a single tool call with before/after hooks."""
    tool_name = tool_call.function.name
    tool_arguments = tool_call.function.arguments

    intercepted = None
    for hook in hooks:
        fn = getattr(hook, "before_tool", None)
        if fn:
            intercepted = fn(tool_name, tool_arguments)
            if intercepted is not None:
                break

    if intercepted is not None:
        tool_result = intercepted
    else:
        tool_result = await _execute_tool_call(tool_name, tool_arguments, tools)

    for hook in hooks:
        fn = getattr(hook, "after_tool", None)
        if fn:
            tool_result = fn(tool_name, tool_arguments, tool_result)

    return {
        "role": "tool",
        "tool_name": tool_name,
        "tool_call_id": tool_call.id,
        "content": tool_result,
    }


async def run_turn(
    history: ConversationHistory,
    agent: Agent,
    *,
    hooks: list[Any] | None = None,
) -> str | None:
    """Executes a chat loop with the LLM, handling tool calls.

    Streaming is handled via publish_event; this function drives the loop
    and mutates *history* in place.

    Args:
        history: The conversation history to read from and append to.
        agent: The agent providing model, tools, options, and think flag.
        hooks: Pluggable hooks invoked at six phases of the turn.

    Returns:
        The final assistant message content, or None if no content was produced.

    Raises:
        ToolLoopError: If an unexpected error occurs in the tool loop.
    """
    provider = get_provider()
    tools = list(agent.tools or [])
    if hooks is None:
        hooks = []

    for hook in hooks:
        fn = getattr(hook, "on_turn_start", None)
        if fn:
            fn(agent.name)

    final_content: str | None = None
    iteration = 0
    try:
        while True:
            iteration += 1

            try:
                # ── before_model hooks ───────────────────────────────────
                for hook in hooks:
                    fn = getattr(hook, "before_model", None)
                    if fn:
                        await fn(history, iteration, agent.name)

                # Stream deltas to frontend as tokens arrive
                response: ChatResponse | None = None
                streamed_deltas = False
                async for chunk in _stream_chat_with_retries(
                    provider, agent=agent, messages=history.messages, tools=tools,
                ):
                    if isinstance(chunk, ChatDelta):
                        streamed_deltas = True
                        try:
                            publish_event(AssistantResponse(
                                content=chunk.content,
                                thinking=chunk.thinking,
                                delta=True,
                            ))
                        except Exception:  # pragma: no cover - defensive
                            logger.exception("Failed to publish delta event")
                    elif isinstance(chunk, ChatResponse):
                        response = chunk

                if response is None:
                    raise ToolLoopError("No ChatResponse received from provider")

                # ── after_model hooks (chain: each can rewrite response) ─
                for hook in hooks:
                    fn = getattr(hook, "after_model", None)
                    if fn:
                        response = await fn(response, history, iteration, agent.name)

                content = response.message.content
                thinking = response.message.thinking
                tool_calls = response.message.tool_calls
                # Serialize tool calls to plain dicts for history storage so
                # providers can reconstruct their own types on the next turn.
                serialized_tool_calls = (
                    [tc.model_dump() for tc in tool_calls] if tool_calls else None
                )
                assistant_message = {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": serialized_tool_calls,
                    "thinking": thinking if agent.persist_thinking else None,
                    "agent_name": get_current_agent_name(),
                }
                history.append(assistant_message)
                # Emit full content only if no deltas were streamed (fallback path)
                if not streamed_deltas:
                    try:
                        publish_event(AssistantResponse(content=content, thinking=thinking))
                    except Exception:  # pragma: no cover - defensive
                        logger.exception("Failed to publish model AssistantResponse event")
                if content is not None:
                    final_content = content

                if not tool_calls:
                    _publish_final()
                    return final_content

                for tc in tool_calls:
                    result = await _run_tool_with_hooks(tc, tools, hooks)
                    history.append(result)

            except StopRequestedError:
                logger.info("Agent '%s' tool loop stopped by user request", agent.name)
                _publish_final()
                return final_content
            except Exception as exc:
                logger.exception("Unhandled exception in tool loop")
                error_msg = "An error occurred while processing your message."
                _publish_final(content=error_msg)
                raise ToolLoopError(error_msg) from exc
    finally:
        for hook in hooks:
            fn = getattr(hook, "on_turn_end", None)
            if fn:
                try:
                    fn(final_content, agent.name)
                except Exception:  # pragma: no cover - defensive
                    logger.exception("on_turn_end hook failed")
