"""Tool loop utilities for executing chat-based LLM interactions with tool calls."""

import inspect
import json
import logging
from collections.abc import AsyncGenerator, Callable, Mapping, Sequence
from typing import Any

from ollama import AsyncClient, ChatResponse

from config import load_config

from .events import AssistantResponse, ToolCallPayload, publish_event
from .tools import _normalize_tool_result, _prepare_tool_arguments


class ToolLoopError(Exception):
    """Custom exception for errors in the tool loop."""


logger = logging.getLogger(__name__)


async def _chat_with_retries(
    client: AsyncClient,
    *,
    model: str,
    messages: list[dict[str, Any]],
    options: Mapping[str, Any] | None,
    tools: Sequence[Callable[..., Any]] | None,
    think: bool,
    retries: int = 20,
) -> ChatResponse:
    """Call client.chat with simple retries and no backoff.

    Args:
        client (AsyncClient): The Ollama async client instance.
        model (str): The model to use.
        messages (list[dict[str, Any]]): The chat messages payload.
        options (Mapping[str, Any] | None): Model options.
        tools (Sequence[Callable[..., Any]] | None): Tool functions to expose.
        think (bool): Whether to use "think" option.
        retries (int): Number of retry attempts after the initial try. Defaults to 20.

    Returns:
        ChatResponse: The successful chat response.

    Raises:
        Exception: The last exception raised by client.chat after exhausting retries.
    """
    attempt = 0
    total_attempts = 1 + max(0, retries)
    while attempt < total_attempts:
        try:
            return await client.chat(
                model=model,
                messages=messages,
                options=options,
                tools=tools or [],
                stream=False,
                think=think,
            )
        except Exception as exc:
            attempt += 1
            if attempt >= total_attempts:
                # Exhausted retries, re-raise the last exception
                raise
            logger.warning(
                "client.chat failed (attempt %s/%s): %s",
                attempt,
                total_attempts,
                exc,
            )
    # Should never reach here, but for type safety, raise an error
    msg = "Failed to get chat response after retries."
    raise ToolLoopError(msg)


async def run_tool_call_loop(
    messages: list[dict[str, Any]],
    tools: Sequence[Callable[..., Any]] | None = None,
    model: str = "",
    model_options: Mapping[str, Any] | None = None,
    *,
    think: bool = False,
    before_model_callbacks: list[Callable[[list[dict[str, Any]]], None]] | None = None,
    after_model_callbacks: list[Callable[[ChatResponse], None]] | None = None,
) -> AsyncGenerator[tuple[str | None, str | None]]:
    """Executes a chat loop with the LLM, handling tool calls and yielding message content.

    This function mutates the messages list in place by appending assistant and tool messages
    to maintain chat history.

    Args:
        messages (list[dict[str, Any]]): The chat history (including system message).
        tools (Optional[Sequence[Callable[..., Any]]]): Sequence of tool functions to use for tool calls.
        model (str): The model name to use for the LLM.
        model_options (Mapping[str, Any] | None): Options to pass to the LLM.
        think (bool): Whether to enable the 'think' option for the model.
        before_model_callbacks (list[Callable[[list[dict[str, Any]]], None]] | None): List of callbacks before model call.
        after_model_callbacks (list[Callable[[ChatResponse], None]] | None): List of callbacks after model call.


    Yields:
        tuple[str | None, str | None]: The message content and thinking as they are generated.

    Raises:
    ToolLoopError: If an unexpected error occurs in the tool loop.

    """  # noqa: E501
    cfg = load_config()
    client = AsyncClient(host=cfg.llm.host) if getattr(cfg, "llm", None) and cfg.llm.host else AsyncClient()
    tools = tools or []
    while True:
        if before_model_callbacks:
            for before_cb in before_model_callbacks:
                before_cb(list(messages))
        try:
            # Call model with internal retry handling
            response = await _chat_with_retries(
                client,
                model=model,
                messages=messages,
                options=model_options,
                tools=tools,
                think=think,
            )
            if after_model_callbacks:
                for after_cb in after_model_callbacks:
                    after_cb(response)

            content = response.message.content
            thinking = response.message.thinking
            tool_calls = response.message.tool_calls
            assistant_message = {
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls,
                "thinking": thinking,
            }
            messages.append(assistant_message)
            # Emit an event for model content/thinking (non-final, actual final decided by loop end)
            try:
                publish_event(AssistantResponse(content=content, thinking=thinking))
            except Exception:  # pragma: no cover - defensive
                logger.exception("Failed to publish model AssistantResponse event")
            if content is not None or thinking is not None:
                yield content, thinking

            if not tool_calls:
                # Normal completion path: no further tool calls. Emit a terminal
                # AssistantResponse with final=True so downstream consumers can
                # detect completion without relying on EOF. This is the ONLY
                # location in the codebase that sets final=True for successful
                # runs (centralized per Phase 2 plan).
                try:
                    publish_event(AssistantResponse(final=True))
                except Exception:  # pragma: no cover - defensive
                    logger.exception("Failed to publish terminal AssistantResponse event")
                break

            for tool_call in tool_calls:
                function = getattr(tool_call, "function", None)
                if not function:
                    logger.warning("Tool call missing function: %s", tool_call)
                    continue
                tool_name = getattr(function, "name", None)
                arguments = getattr(function, "arguments", {})

                try:
                    publish_event(AssistantResponse(event=ToolCallPayload(type="tool_call", name=str(tool_name))))
                except Exception:  # pragma: no cover - defensive
                    logger.exception("Failed to publish tool_call event for tool '%s'", tool_name)

                tool_func = next(
                    (tool for tool in tools if getattr(tool, "__name__", None) == tool_name),
                    None,
                )
                if not tool_func:
                    logger.error("Tool '%s' not found in tools.", tool_name)
                    tool_result: dict[str, Any] = {"error": "Tool not found"}
                else:
                    try:
                        validated_args = _prepare_tool_arguments(tool_func, arguments)
                        if inspect.iscoroutinefunction(tool_func):
                            result = await tool_func(**validated_args)
                        else:
                            result = tool_func(**validated_args)
                        serializable_result = _normalize_tool_result(result)
                        tool_result = {"result": serializable_result}
                    except (ValueError, TypeError, json.JSONDecodeError) as exc:
                        logger.exception("Argument validation failed for tool '%s'", tool_name)
                        tool_result = {"error": f"Argument validation failed: {exc}"}
                    except Exception as exc:
                        logger.exception("Error running tool '%s'", tool_name)
                        tool_result = {"error": str(exc)}
                tool_message = {
                    "role": "tool",
                    "tool_name": tool_name,
                    "content": json.dumps(tool_result),
                }
                messages.append(tool_message)
            # Do not yield tool results, just continue looping
        except Exception as exc:
            # Error path: still emit a final event (single source of final=True)
            # with a generic error message before propagating as ToolLoopError.
            logger.exception("Unhandled exception in tool loop")
            error_msg = "An error occurred while processing your message."
            try:
                publish_event(AssistantResponse(content=error_msg, final=True))
            except Exception:  # pragma: no cover - defensive
                logger.exception("Failed to publish terminal error AssistantResponse event")
            raise ToolLoopError(error_msg) from exc
