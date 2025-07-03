import json
import logging
import pprint
import re
from collections.abc import AsyncGenerator, Callable, Sequence
from typing import Mapping, Any

logger = logging.getLogger(__name__)

# --- Utility Functions ---

def _strip_think_tags(text: str) -> str:
    """
    Remove all <think>...</think> tags and their contents from the given text.

    Args:
        text (str): The input string possibly containing <think> tags.

    Returns:
        str: The string with all <think>...</think> blocks removed.
    """
    return re.sub(r'<think>[\s\S]*?</think>', '', text, flags=re.IGNORECASE).strip()

async def run_tool_call_loop(
    messages: list[dict[str, str]],
    tools: list[Callable[..., object]],
    model: str = '',
    model_options: Mapping[str, Any] | None = None,
    client=None
) -> AsyncGenerator[str, None]:
    """
    Executes a chat loop with the LLM, handling tool calls and yielding message content.
    This function mutates the messages list in place by appending assistant and tool messages.

    Args:
        messages (list[dict[str, str]]): The chat history (including system message). This list is mutated in place.
        tools (list[Callable[..., object]]): List of tool functions to use for tool calls.
        model (str): The model name to use for the LLM.
        model_options (Mapping[str, Any] | None): Options to pass to the LLM.
        client: The LLM client instance (must have an async chat method).

    Yields:
        str: The message content at each step (never tool call results directly).
    """
    opts = dict(model_options) if model_options else {}
    if client is None:
        try:
            from ollama import AsyncClient
            client = AsyncClient()
        except ImportError as exc:
            logger.error("Ollama AsyncClient not available: %s", exc)
            raise
    while True:
        logger.debug("\033[32mChat history sent to LLM:\n%s\033[0m", pprint.pformat(messages))
        try:
            response = await client.chat(
                model=model,
                messages=messages,
                options=opts,
                tools=tools,
                stream=False,
            )
            # Log LLM stats if present
            if hasattr(response, 'done') and getattr(response, 'done', False):
                # Extract and convert durations from ns to s
                total_duration_ns = getattr(response, 'total_duration', None)
                load_duration_ns = getattr(response, 'load_duration', None)
                prompt_eval_count = getattr(response, 'prompt_eval_count', None)
                prompt_eval_duration_ns = getattr(response, 'prompt_eval_duration', None)
                eval_count = getattr(response, 'eval_count', None)
                eval_duration_ns = getattr(response, 'eval_duration', None)
                def ns_to_s(ns):
                    return ns / 1_000_000_000 if ns is not None else None
                total_duration = ns_to_s(total_duration_ns)
                load_duration = ns_to_s(load_duration_ns)
                prompt_eval_duration = ns_to_s(prompt_eval_duration_ns)
                eval_duration = ns_to_s(eval_duration_ns)
                # Calculate tokens/sec
                prompt_tokens_per_sec = (prompt_eval_count / prompt_eval_duration) if (prompt_eval_count and prompt_eval_duration) else None
                eval_tokens_per_sec = (eval_count / eval_duration) if (eval_count and eval_duration) else None
                # Log nicely, with newlines for readability
                logger.info(
                    "\nLLM stats:\n"
                    f"  total_duration:         {total_duration:.3f}s\n"
                    f"  load_duration:          {load_duration:.3f}s\n"
                    f"  prompt_eval_count:      {prompt_eval_count}\n"
                    f"  prompt_eval_duration:   {prompt_eval_duration:.3f}s\n"
                    f"  prompt_tokens_per_sec:  {prompt_tokens_per_sec:.2f}\n"
                    f"  eval_count:             {eval_count}\n"
                    f"  eval_duration:          {eval_duration:.3f}s\n"
                    f"  eval_tokens_per_sec:    {eval_tokens_per_sec:.2f}\n"
                )
            try:
                # Use model_dump for pretty printing if available (Pydantic BaseModel)
                response_data = response.model_dump()
                logger.debug("\033[33mLLM response:\n%s\033[0m", pprint.pformat(response_data))
            except Exception as exc:
                logger.debug("\033[33mLLM response (raw): %r\033[0m", response)
            content = response.message.content or ""
            tool_calls = getattr(response.message, 'tool_calls', None)
            yield content.strip()
            if not tool_calls:
                break
            assistant_message = {
                'role': 'assistant',
                'content': _strip_think_tags(content),
                'tool_calls': tool_calls
            }
            messages.append(assistant_message)
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
                        result = tool_func(**arguments)
                        # Ensure result is JSON serializable
                        if hasattr(result, 'model_dump'):
                            serializable_result = result.model_dump() # type: ignore
                        elif hasattr(result, 'dict'):
                            serializable_result = result.dict() # type: ignore
                        elif isinstance(result, (str, int, float, bool, type(None), list, dict)):
                            serializable_result = result
                        else:
                            serializable_result = str(result)
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

__all__ = ["run_tool_call_loop", "_strip_think_tags"]
