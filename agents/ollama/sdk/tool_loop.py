"""Tool loop utilities for executing chat-based LLM interactions with tool calls."""

import inspect
import json
import logging
from collections.abc import AsyncGenerator, Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from ollama import AsyncClient, ChatResponse
from pydantic import BaseModel

from config import load_config

from .events import AssistantResponse, ToolCallPayload, publish_event


class ToolLoopError(Exception):
    """Custom exception for errors in the tool loop."""


logger = logging.getLogger(__name__)


@runtime_checkable
class _HasDict(Protocol):
    def dict(self) -> Mapping[str, object]:  # pragma: no cover - protocol
        ...


def _to_serializable(obj: object) -> object:
    """Recursively convert Pydantic models and custom objects to JSON-serializable dicts.

    Args:
        obj (Any): The object to convert.

    Returns:
        Any: JSON-serializable representation.

    """
    if isinstance(obj, BaseModel):
        return _to_serializable(obj.model_dump())
    if isinstance(obj, _HasDict):
        return _to_serializable(obj.dict())
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple | set):
        return [_to_serializable(i) for i in obj]
    return obj


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


def _validate_tool_arguments(
    tool_func: Callable[..., Any], arguments: dict[str, Any]
) -> dict[str, Any]:
    """Validate and convert tool function arguments according to type hints.

    Args:
        tool_func (Callable[..., Any]): The tool function to validate arguments for.
        arguments (dict[str, Any]): The raw arguments from the tool call.

    Returns:
        dict[str, Any]: The validated and converted arguments.

    Raises:
        ValueError: If argument validation fails.
        TypeError: If argument type conversion fails.
        json.JSONDecodeError: If JSON parsing fails for Pydantic objects.

    """
    validated_args = {}
    sig = inspect.signature(tool_func)

    for arg_name, param in sig.parameters.items():
        expected_type = param.annotation
        value = arguments.get(arg_name, param.default)

        # Skip validation if parameter has no default and is missing from arguments
        if value is inspect.Parameter.empty:
            msg = f"Required parameter '{arg_name}' is missing"
            raise ValueError(msg)

        if expected_type is not inspect.Parameter.empty:
            origin = getattr(expected_type, "__origin__", None)
            if origin is not None and origin is type(None):
                validated_args[arg_name] = value
            elif origin is list:
                # Handle list[SomeModel] types
                args = getattr(expected_type, "__args__", ())
                if args and len(args) == 1:
                    item_type = args[0]
                    if hasattr(item_type, "model_validate") or hasattr(item_type, "parse_obj"):
                        # Convert list of dicts to list of Pydantic models
                        validated_list = []
                        for item_value in value:
                            parsed_item = item_value
                            if isinstance(item_value, str):
                                parsed_item = json.loads(item_value)
                            if hasattr(item_type, "model_validate"):
                                validated_list.append(item_type.model_validate(parsed_item))
                            else:  # Fallback for older Pydantic
                                validated_list.append(item_type.parse_obj(parsed_item))
                        validated_args[arg_name] = validated_list
                    else:
                        validated_args[arg_name] = value
                else:
                    validated_args[arg_name] = value
            elif hasattr(expected_type, "model_validate"):
                if isinstance(value, str):
                    value = json.loads(value)
                validated_args[arg_name] = expected_type.model_validate(value)
            elif hasattr(expected_type, "parse_obj"):  # Fallback for older Pydantic
                if isinstance(value, str):
                    value = json.loads(value)
                validated_args[arg_name] = expected_type.parse_obj(value)
            elif expected_type is str:
                validated_args[arg_name] = str(value)
            elif expected_type is int:
                validated_args[arg_name] = int(value)
            elif expected_type is float:
                validated_args[arg_name] = float(value)
            elif expected_type is bool:
                validated_args[arg_name] = bool(value)
            else:
                validated_args[arg_name] = value
        else:
            validated_args[arg_name] = value

    return validated_args


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
    if getattr(cfg, "llm", None) and cfg.llm.host:
        client = AsyncClient(host=cfg.llm.host)
    else:
        client = AsyncClient()
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
                break
            for tool_call in tool_calls:
                function = getattr(tool_call, "function", None)
                if not function:
                    logger.warning("Tool call missing function: %s", tool_call)
                    continue
                tool_name = getattr(function, "name", None)
                arguments = getattr(function, "arguments", {})
                # Emit a tool_call event prior to executing the tool
                try:
                    publish_event(
                        AssistantResponse(
                            event=ToolCallPayload(type="tool_call", name=str(tool_name))
                        )
                    )
                except Exception:  # pragma: no cover - defensive
                    logger.exception("Failed to publish tool_call event for tool '%s'", tool_name)
                tool_func = next(
                    (tool for tool in tools if getattr(tool, "__name__", None) == tool_name),
                    None,
                )
                if not tool_func:
                    logger.error("Tool '%s' not found in tools.", tool_name)
                    tool_result = {"error": "Tool not found"}
                else:
                    try:
                        validated_args = _validate_tool_arguments(tool_func, arguments)
                        if inspect.iscoroutinefunction(tool_func):
                            result = await tool_func(**validated_args)
                        else:
                            result = tool_func(**validated_args)
                        serializable_result = _to_serializable(result)
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
            logger.exception("Unhandled exception in tool loop")
            msg = "An error occurred while processing your message."
            raise ToolLoopError(msg) from exc
