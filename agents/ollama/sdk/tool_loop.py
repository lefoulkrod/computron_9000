import json
import logging
import pprint
import re
import inspect
from collections.abc import AsyncGenerator, Callable, Sequence
from typing import Mapping, Any, Optional, Callable as TypingCallable

from ollama import AsyncClient, ChatResponse
from pydantic import BaseModel

from agents.ollama.sdk.extract_thinking import split_think_content

logger = logging.getLogger(__name__)

# --- Pydantic Model for LLM Stats ---

class _LLMRuntimeStats(BaseModel):
    total_duration: Optional[float] = None
    load_duration: Optional[float] = None
    prompt_eval_count: Optional[int] = None
    prompt_eval_duration: Optional[float] = None
    prompt_tokens_per_sec: Optional[float] = None
    eval_count: Optional[int] = None
    eval_duration: Optional[float] = None
    eval_tokens_per_sec: Optional[float] = None

# --- Utility Functions ---

def _llm_runtime_stats(response: object) -> _LLMRuntimeStats:
    """
    Extracts and converts LLM runtime statistics from the response object.

    Args:
        response (object): The LLM response object with runtime attributes.

    Returns:
        _LLMRuntimeStats: Parsed and converted runtime statistics.
    """
    def ns_to_s(ns: Optional[int]) -> Optional[float]:
        return ns / 1_000_000_000 if ns is not None else None

    total_duration = ns_to_s(getattr(response, 'total_duration', None))
    load_duration = ns_to_s(getattr(response, 'load_duration', None))
    prompt_eval_count = getattr(response, 'prompt_eval_count', None)
    prompt_eval_duration = ns_to_s(getattr(response, 'prompt_eval_duration', None))
    eval_count = getattr(response, 'eval_count', None)
    eval_duration = ns_to_s(getattr(response, 'eval_duration', None))
    prompt_tokens_per_sec = (prompt_eval_count / prompt_eval_duration) if (prompt_eval_count and prompt_eval_duration) else None
    eval_tokens_per_sec = (eval_count / eval_duration) if (eval_count and eval_duration) else None
    return _LLMRuntimeStats(
        total_duration=total_duration,
        load_duration=load_duration,
        prompt_eval_count=prompt_eval_count,
        prompt_eval_duration=prompt_eval_duration,
        prompt_tokens_per_sec=prompt_tokens_per_sec,
        eval_count=eval_count,
        eval_duration=eval_duration,
        eval_tokens_per_sec=eval_tokens_per_sec,
    )

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
    before_model_call: TypingCallable[[list[dict[str, str]]], None] | None = None,
    after_model_call: TypingCallable[["ChatResponse"], None] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Executes a chat loop with the LLM, handling tool calls and yielding message content.
    This function mutates the messages list in place by appending assistant and tool messages to maintain chat history.

    Args:
        messages (list[dict[str, str]]): The chat history (including system message). This list is mutated in place.
        tools (list[Callable[..., object]]): List of tool functions to use for tool calls.
        model (str): The model name to use for the LLM.
        model_options (Mapping[str, Any] | None): Options to pass to the LLM.
        before_model_call (Callable[[list[dict[str, str]]], None] | None): Callback before model call.
        after_model_call (Callable[[ChatResponse], None] | None): Callback after model call.

    Yields:
        str: The message content at each step (never tool call results directly).
    """
    opts = dict(model_options) if model_options else {}
    client = AsyncClient()
    while True:
        if before_model_call:
            before_model_call(list(messages))
        try:
            response = await client.chat(
                model=model,
                messages=messages,
                options=opts,
                tools=tools,
                stream=False,
            )
            if after_model_call:
                after_model_call(response)
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