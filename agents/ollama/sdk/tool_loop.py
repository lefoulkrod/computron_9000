"""Tool loop utilities for executing chat-based LLM interactions with tool calls."""

import inspect
import json
import logging
from collections.abc import AsyncGenerator, Callable, Mapping, Sequence
from typing import Any

from ollama import AsyncClient, ChatResponse

from agents.ollama.sdk.extract_thinking import split_think_content

logger = logging.getLogger(__name__)

# --- Utility Functions ---


def _to_serializable(obj: Any) -> Any:
    """Recursively convert Pydantic models and custom objects to JSON-serializable dicts.

    Args:
        obj (Any): The object to convert.

    Returns:
        Any: JSON-serializable representation.

    """
    if hasattr(obj, "model_dump"):
        return _to_serializable(obj.model_dump())
    if hasattr(obj, "dict"):
        return _to_serializable(obj.dict())
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple | set):
        return [_to_serializable(i) for i in obj]
    return obj


async def run_tool_call_loop(
    messages: list[dict[str, Any]],
    tools: Sequence[Callable[..., Any]] | None = None,
    model: str = "",
    model_options: Mapping[str, Any] | None = None,
    before_model_callbacks: list[Callable[[list[dict[str, Any]]], None]] | None = None,
    after_model_callbacks: list[Callable[[ChatResponse], None]] | None = None,
) -> AsyncGenerator[str, None]:
    """Executes a chat loop with the LLM, handling tool calls and yielding message content.

    This function mutates the messages list in place by appending assistant and tool messages
    to maintain chat history.

    Args:
        messages (list[dict[str, Any]]): The chat history (including system message).
        tools (Optional[Sequence[Callable[..., Any]]]): Sequence of tool functions to use for tool calls.
        model (str): The model name to use for the LLM.
        model_options (Mapping[str, Any] | None): Options to pass to the LLM.
        before_model_callbacks (list[Callable[[list[dict[str, Any]]], None]] | None): List of callbacks before model call.
        after_model_callbacks (list[Callable[[ChatResponse], None]] | None): List of callbacks after model call.

    Yields:
        str: The message content at each step (never tool call results directly).

    """  # noqa: E501
    client = AsyncClient()
    tools = tools or []
    while True:
        if before_model_callbacks:
            for before_cb in before_model_callbacks:
                before_cb(list(messages))
        try:
            response = await client.chat(
                model=model,
                messages=messages,
                options=model_options,
                tools=tools,
                stream=False,
            )
            if after_model_callbacks:
                for after_cb in after_model_callbacks:
                    after_cb(response)
            content = response.message.content or None
            tool_calls = response.message.tool_calls or None
            # Remove thinking content from the response before storing in chat history
            content_without_think = split_think_content(content)[0] if content else None
            assistant_message = {
                "role": "assistant",
                "content": content_without_think,
                "tool_calls": tool_calls,
            }
            messages.append(assistant_message)
            if content:
                yield content
            if not tool_calls:
                break
            for tool_call in tool_calls:
                function = getattr(tool_call, "function", None)
                if not function:
                    logger.warning("Tool call missing function: %s", tool_call)
                    continue
                tool_name = getattr(function, "name", None)
                arguments = getattr(function, "arguments", {})
                tool_func = next(
                    (tool for tool in tools if getattr(tool, "__name__", None) == tool_name),
                    None,
                )
                if not tool_func:
                    logger.error("Tool '%s' not found in tools.", tool_name)
                    tool_result = {"error": "Tool not found"}
                else:
                    validated_args = {}
                    sig = inspect.signature(tool_func)
                    validation_error = None
                    for arg_name, param in sig.parameters.items():
                        expected_type = param.annotation
                        value = arguments.get(arg_name, param.default)
                        try:
                            if expected_type is not inspect.Parameter.empty:
                                origin = getattr(expected_type, "__origin__", None)
                                if origin is not None and origin is type(None):
                                    validated_args[arg_name] = value
                                elif hasattr(expected_type, "parse_obj"):
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
                        except (ValueError, TypeError, json.JSONDecodeError) as exc:
                            logger.exception(
                                "Argument '%s' failed validation for tool '%s'", arg_name, tool_name
                            )
                            tool_result = {
                                "error": f"Argument '{arg_name}' failed validation: {exc}"
                            }
                            validation_error = True
                            break
                    if not validation_error:
                        try:
                            if inspect.iscoroutinefunction(tool_func):
                                result = await tool_func(**validated_args)
                            else:
                                result = tool_func(**validated_args)
                            serializable_result = _to_serializable(result)
                            tool_result = {"result": serializable_result}
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
            logger.exception("Error: %s", exc)
            yield "An error occurred while processing your message."
            break
