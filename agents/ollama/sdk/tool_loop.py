"""Tool loop utilities for executing chat-based LLM interactions with tool calls."""

import inspect
import json
import logging
from collections.abc import AsyncGenerator, Callable
from typing import Any

from ollama import AsyncClient, ChatResponse

from agents.types import Agent
from config import load_config

from .context import ConversationHistory
from .events import AssistantResponse, StopRequestedError, ToolCallPayload, publish_event
from .tools import _normalize_tool_result, _prepare_tool_arguments


class ToolLoopError(Exception):
    """Custom exception for errors in the tool loop."""


logger = logging.getLogger(__name__)


def _publish_final(content: str | None = None) -> None:
    """Emit a terminal AssistantResponse. Logs but never raises on failure."""
    try:
        publish_event(AssistantResponse(content=content, final=True))
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to publish terminal AssistantResponse event")


async def _chat_with_retries(
    client: AsyncClient,
    *,
    agent: Agent,
    messages: list[dict[str, Any]],
    tools: list[Callable[..., Any]] | None = None,
    retries: int = 20,
) -> ChatResponse:
    """Call client.chat with simple retries and no backoff.

    Args:
        client (AsyncClient): The Ollama async client instance.
        agent (Agent): The agent providing model, options, tools, and think flag.
        messages (list[dict[str, Any]]): The chat messages payload.
        tools: Tool list override. Falls back to ``agent.tools`` when *None*.
        retries (int): Number of retry attempts after the initial try. Defaults to 20.

    Returns:
        ChatResponse: The successful chat response.

    Raises:
        Exception: The last exception raised by client.chat after exhausting retries.
    """
    resolved_tools = tools if tools is not None else (agent.tools or [])
    attempt = 0
    total_attempts = 1 + max(0, retries)
    while attempt < total_attempts:
        try:
            return await client.chat(
                model=agent.model,
                messages=messages,
                options=agent.options,
                tools=resolved_tools,
                stream=False,
                think=agent.think,
            )
        except Exception as exc:
            attempt += 1
            # Log request context so we can diagnose what Ollama choked on
            payload_bytes = sum(len(json.dumps(m)) for m in messages)
            last_role = messages[-1].get("role", "?") if messages else "empty"
            last_content = messages[-1].get("content", "") if messages else ""
            last_preview = (last_content[:200] + "...") if isinstance(last_content, str) and len(last_content) > 200 else last_content  # noqa: E501
            logger.warning(
                "client.chat failed (attempt %s/%s): %s | "
                "model=%s msgs=%d payload≈%dKB last_role=%s last_content=%s",
                attempt,
                total_attempts,
                exc,
                agent.model,
                len(messages),
                payload_bytes // 1024,
                last_role,
                last_preview,
            )
            if attempt >= total_attempts:
                # Exhausted retries, re-raise the last exception
                raise
    # Should never reach here, but for type safety, raise an error
    msg = "Failed to get chat response after retries."
    raise ToolLoopError(msg)


async def _execute_tool_call(
    tool_call: Any,
    tools: list[Callable[..., Any]],
) -> dict[str, Any]:
    """Resolve and execute a single tool call, returning the result message content.

    Args:
        tool_call: The tool call object from the model response.
        tools: Available tool functions to match against.

    Returns:
        A dict with either ``{"result": ...}`` or ``{"error": ...}``.
    """
    function = getattr(tool_call, "function", None)
    if not function:
        logger.warning("Tool call missing function: %s", tool_call)
        return {"error": "Tool call missing function"}

    tool_name = getattr(function, "name", None)
    arguments = getattr(function, "arguments", {})

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
        return {"error": "Tool not found"}

    try:
        validated_args = _prepare_tool_arguments(tool_func, arguments)
        if inspect.iscoroutinefunction(tool_func):
            result = await tool_func(**validated_args)
        else:
            result = tool_func(**validated_args)
        return {"result": _normalize_tool_result(result)}
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        logger.exception("Argument validation failed for tool '%s'", tool_name)
        return {"error": f"Argument validation failed: {exc}"}
    except Exception as exc:
        logger.exception("Error running tool '%s'", tool_name)
        return {"error": str(exc)}


async def run_tool_call_loop(
    history: ConversationHistory,
    agent: Agent,
    *,
    hooks: list[Any] | None = None,
) -> AsyncGenerator[tuple[str | None, str | None]]:
    """Executes a chat loop with the LLM, handling tool calls and yielding message content.

    Args:
        history: The conversation history to read from and append to.
        agent: The agent providing model, tools, options, and think flag.
        hooks: Pluggable hooks invoked at four phases of each iteration.

    Yields:
        tuple[str | None, str | None]: The message content and thinking as they are generated.

    Raises:
        ToolLoopError: If an unexpected error occurs in the tool loop.
    """
    cfg = load_config()
    client = AsyncClient(host=cfg.llm.host) if getattr(cfg, "llm", None) and cfg.llm.host else AsyncClient()
    tools = list(agent.tools or [])
    if hooks is None:
        hooks = []
    iteration = 0
    while True:
        iteration += 1

        # ── before_model hooks ───────────────────────────────────────
        for hook in hooks:
            fn = getattr(hook, "before_model", None)
            if fn:
                fn(history, iteration, agent.name)

        try:
            # Call model with internal retry handling
            response = await _chat_with_retries(
                client,
                agent=agent,
                messages=history.messages,
                tools=tools,
            )

            # ── after_model hooks (chain: each can rewrite response) ─
            for hook in hooks:
                fn = getattr(hook, "after_model", None)
                if fn:
                    response = fn(response, history, iteration, agent.name)

            content = response.message.content
            thinking = response.message.thinking
            tool_calls = response.message.tool_calls
            assistant_message = {
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls,
                "thinking": thinking if agent.persist_thinking else None,
            }
            history.append(assistant_message)
            # Emit an event for model content/thinking (non-final, actual final decided by loop end)
            try:
                publish_event(AssistantResponse(content=content, thinking=thinking))
            except Exception:  # pragma: no cover - defensive
                logger.exception("Failed to publish model AssistantResponse event")
            if content is not None or thinking is not None:
                yield content, thinking

            if not tool_calls:
                _publish_final()
                break

            for tool_call in tool_calls:
                function = getattr(tool_call, "function", None)
                tool_name = getattr(function, "name", None) if function else None
                tool_arguments = getattr(function, "arguments", {}) if function else {}

                # ── before_tool hooks ────────────────────────────────
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
                    tool_result = await _execute_tool_call(tool_call, tools)

                # ── after_tool hooks (chain: each rewrites result) ───
                for hook in hooks:
                    fn = getattr(hook, "after_tool", None)
                    if fn:
                        tool_result = fn(tool_name, tool_arguments, tool_result)

                history.append({
                    "role": "tool",
                    "tool_name": tool_name,
                    "content": json.dumps(tool_result),
                })

        except StopRequestedError:
            logger.info("Tool loop stopped by user request")
            _publish_final()
            return
        except Exception as exc:
            logger.exception("Unhandled exception in tool loop")
            error_msg = "An error occurred while processing your message."
            _publish_final(content=error_msg)
            raise ToolLoopError(error_msg) from exc
