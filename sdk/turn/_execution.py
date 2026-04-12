"""Tool loop utilities for executing chat-based LLM interactions with tool calls."""

import asyncio
import logging
from collections.abc import AsyncGenerator, Callable
from typing import Any

from agents.types import Agent
from sdk.context import ConversationHistory
from sdk.events import AgentEvent, ContentPayload, TurnEndPayload, get_current_agent_name, publish_event
from sdk.providers import ChatDelta, ChatResponse, ProviderError, get_provider
from sdk.skills.agent_state import _active_agent_state
from sdk.tools import _execute_tool_call

from ._turn import StopRequestedError


def _get_parallel_config():
    """Lazy-load parallel config to avoid circular imports at module level."""
    from config import load_config

    return load_config().parallel


class ToolLoopError(Exception):
    """Custom exception for errors in the tool loop."""


logger = logging.getLogger(__name__)


def _publish_turn_end() -> None:
    """Emit a TurnEndPayload. Logs but never raises on failure."""
    try:
        publish_event(AgentEvent(payload=TurnEndPayload(type="turn_end")))
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to publish turn_end event")


async def _stream_chat_with_retries(
    provider: Any,
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[Callable[..., Any]],
    options: dict[str, Any] | None = None,
    think: bool = False,
    retries: int = 5,
) -> AsyncGenerator[ChatDelta | ChatResponse, None]:
    """Yield ChatDelta tokens, then the final ChatResponse. Retries on failure.

    If a stream fails mid-way after emitting deltas, retrying would cause
    content duplication. On retry, fall back to non-streaming chat() to
    yield a single complete ChatResponse instead.
    """
    attempt = 0
    total_attempts = 1 + max(0, retries)
    while attempt < total_attempts:
        try:
            if attempt == 0:
                async for chunk in provider.chat_stream(
                    model=model,
                    messages=messages,
                    options=options,
                    tools=tools,
                    think=think,
                ):
                    yield chunk
            else:
                # Retry with non-streaming to avoid content duplication
                yield await provider.chat(
                    model=model,
                    messages=messages,
                    options=options,
                    tools=tools,
                    think=think,
                )
            return
        except ProviderError as exc:
            attempt += 1
            if not exc.retryable:
                logger.error(
                    "provider.chat_stream failed (non-retryable): %s | model=%s",
                    exc,
                    model,
                )
                raise
            delay = min(2**attempt, 32)
            logger.warning(
                "provider.chat_stream failed (attempt %s/%s, retryable, backoff %ds): %s | model=%s",
                attempt,
                total_attempts,
                delay,
                exc,
                model,
            )
            if attempt >= total_attempts:
                raise
            await asyncio.sleep(delay)
        except Exception as exc:
            logger.error(
                "provider.chat_stream failed (unexpected): %s | model=%s",
                exc,
                model,
            )
            raise
    msg = "Failed to get chat response after retries."
    raise ToolLoopError(msg)


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
    """Executes a single turn with the LLM, handling tool calls.

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
    agent_state = _active_agent_state.get()
    if agent_state is None:
        raise ToolLoopError("run_turn called outside an agent_span (no active AgentState)")
    if hooks is None:
        hooks = []

    for hook in hooks:
        fn = getattr(hook, "on_turn_start", None)
        if fn:
            fn(agent.name)

    parallel_cfg = _get_parallel_config()
    final_content: str | None = None
    iteration = 0
    try:
        while True:
            iteration += 1
            logger.debug("Tool loop iteration %d for agent '%s'", iteration, agent.name)

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
                    provider,
                    model=agent.model,
                    messages=history.messages,
                    tools=agent_state.tools,
                    options=agent.options,
                    think=agent.think,
                ):
                    if isinstance(chunk, ChatDelta):
                        streamed_deltas = True
                        try:
                            publish_event(AgentEvent(payload=ContentPayload(
                                type="content",
                                content=chunk.content,
                                thinking=chunk.thinking,
                                delta=True,
                            )))
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
                serialized_tool_calls = [tc.model_dump() for tc in tool_calls] if tool_calls else None
                assistant_message = {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": serialized_tool_calls,
                    "thinking": thinking,
                    "agent_name": get_current_agent_name(),
                }
                history.append(assistant_message)
                # Emit full content only if no deltas were streamed (fallback path)
                if not streamed_deltas:
                    try:
                        publish_event(AgentEvent(payload=ContentPayload(
                            type="content", content=content, thinking=thinking,
                        )))
                    except Exception:  # pragma: no cover - defensive
                        logger.exception("Failed to publish model AgentEvent event")
                if content is not None:
                    final_content = content

                if not tool_calls:
                    _publish_turn_end()
                    return final_content

                tool_names = [tc.function.name for tc in tool_calls]
                logger.debug("Executing %d tool call(s) for '%s': %s", len(tool_calls), agent.name, tool_names)

                if parallel_cfg.enabled and len(tool_calls) > 1:
                    logger.info(
                        "Running %d tool calls in parallel for '%s' (max_concurrent=%d)",
                        len(tool_calls),
                        agent.name,
                        parallel_cfg.max_concurrent,
                    )
                    sem = asyncio.Semaphore(parallel_cfg.max_concurrent)

                    async def _run_parallel(tc_item):
                        async with sem:
                            return tc_item, await _run_tool_with_hooks(tc_item, agent_state.tools, hooks)

                    tasks = [asyncio.create_task(_run_parallel(tc)) for tc in tool_calls]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for tc, result in zip(tool_calls, results):
                        if isinstance(result, Exception):
                            logger.error("Parallel tool call failed: %s", result)
                            history.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc.id,
                                    "tool_name": tc.function.name,
                                    "content": "Error: %s" % result,
                                }
                            )
                        else:
                            _tc, tool_result = result
                            history.append(tool_result)
                else:
                    for tc in tool_calls:
                        result = await _run_tool_with_hooks(tc, agent_state.tools, hooks)
                        history.append(result)

            except StopRequestedError:
                logger.info("Agent '%s' tool loop stopped by user request", agent.name)
                _publish_turn_end()
                raise
            except Exception as exc:
                logger.exception("Unhandled exception in tool loop")
                error_msg = "An error occurred while processing your message."
                publish_event(AgentEvent(payload=ContentPayload(type="content", content=error_msg)))
                _publish_turn_end()
                raise ToolLoopError(error_msg) from exc
    finally:
        for hook in hooks:
            fn = getattr(hook, "on_turn_end", None)
            if fn:
                try:
                    fn(final_content, agent.name)
                except Exception:  # pragma: no cover - defensive
                    logger.exception("on_turn_end hook failed")
