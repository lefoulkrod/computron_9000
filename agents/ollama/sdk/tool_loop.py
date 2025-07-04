import json
import logging
import inspect
from collections.abc import AsyncGenerator, Callable
from typing import Mapping, Any

from ollama import AsyncClient, ChatResponse

from agents.ollama.sdk.extract_thinking import split_think_content

logger = logging.getLogger(__name__)

# --- Utility Functions ---

def _to_serializable(obj: Any) -> Any:
    """
    Recursively convert Pydantic models and custom objects to JSON-serializable dicts.

    Args:
        obj (Any): The object to convert.

    Returns:
        Any: JSON-serializable representation.
    """
    if hasattr(obj, 'model_dump'):
        return _to_serializable(obj.model_dump())
    if hasattr(obj, 'dict'):
        return _to_serializable(obj.dict())
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [ _to_serializable(i) for i in obj ]
    return obj

async def run_tool_call_loop(
    messages: list[dict[str, str]],
    tools: list[Callable[..., object]],
    model: str = '',
    model_options: Mapping[str, Any] | None = None,
    before_model_callbacks: list[Callable[[list[dict[str, str]]], None]] | None = None,
    after_model_callbacks: list[Callable[[ChatResponse], None]] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Executes a chat loop with the LLM, handling tool calls and yielding message content.
    This function mutates the messages list in place by appending assistant and tool messages to maintain chat history.

    Args:
        messages (list[dict[str, str]]): The chat history (including system message). This list is mutated in place.
        tools (list[Callable[..., object]]): List of tool functions to use for tool calls.
        model (str): The model name to use for the LLM.
        model_options (Mapping[str, Any] | None): Options to pass to the LLM.
        before_model_callbacks (list[Callable[[list[dict[str, str]]], None]] | None): List of callbacks before model call.
        after_model_callbacks (list[Callable[[ChatResponse], None]] | None): List of callbacks after model call.

    Yields:
        str: The message content at each step (never tool call results directly).
    """
    opts = dict(model_options) if model_options else {}
    client = AsyncClient()
    while True:
        if before_model_callbacks:
            for cb in before_model_callbacks:
                cb(list(messages))
        try:
            response = await client.chat(
                model=model,
                messages=messages,
                options=opts,
                tools=tools,
                stream=False,
            )
            if after_model_callbacks:
                for cb in after_model_callbacks:
                    cb(response)
            content = response.message.content or ""
            tool_calls = getattr(response.message, 'tool_calls', None)
            yield content.strip()
            assistant_message = {
                'role': 'assistant',
                'content': split_think_content(content)[0],
                'tool_calls': tool_calls
            }
            messages.append(assistant_message)
            if not tool_calls:
                break
            for tool_call in tool_calls:
                function = getattr(tool_call, 'function', None)
                if not function:
                    logger.warning("Tool call missing function: %s", tool_call)
                    continue
                tool_name = getattr(function, 'name', None)
                arguments = getattr(function, 'arguments', {})
                tool_func = next((tool for tool in tools if getattr(tool, '__name__', None) == tool_name), None)
                if not tool_func:
                    logger.error("Tool '%s' not found in tools.", tool_name)
                    tool_result = {"error": "Tool not found"}
                else:
                    try:
                        if inspect.iscoroutinefunction(tool_func):
                            result = await tool_func(**arguments)
                        else:
                            result = tool_func(**arguments)
                        # Ensure result is JSON serializable
                        serializable_result = _to_serializable(result)
                        tool_result = {"result": serializable_result}
                    except Exception as exc:
                        logger.exception(f"Error running tool '{tool_name}': {exc}")
                        tool_result = {"error": str(exc)}
                tool_message = {
                    'role': 'tool',
                    'name': tool_name,
                    'content': json.dumps(tool_result)
                }
                messages.append(tool_message)
            # Do not yield tool results, just continue looping
        except Exception as exc:
            logger.exception("Error: %s", exc)
            yield "An error occurred while processing your message."
            break