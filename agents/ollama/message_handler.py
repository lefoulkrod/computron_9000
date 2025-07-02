import json
import logging
import pprint
import re
from collections.abc import Callable
from typing import AsyncGenerator, Sequence, Mapping, Any

from ollama import AsyncClient

from agents.types import UserMessageEvent, Data
from config import load_config
from .agents import computron

logger = logging.getLogger(__name__)

config = load_config()

# Module-level message history for chat session, initialized with system message
_message_history: list[dict[str, str]] = [
    {'role': 'system', 'content': computron.instruction}
]

def _strip_think_tags(text: str) -> str:
    """
    Remove all <think>...</think> tags and their contents from the given text.

    Args:
        text (str): The input string possibly containing <think> tags.

    Returns:
        str: The string with all <think>...</think> blocks removed.
    """
    return re.sub(r'<think>[\s\S]*?</think>', '', text, flags=re.IGNORECASE).strip()

async def handle_user_message(
    message: str,
    data: Sequence[Data] | None = None, 
    stream: bool = False
) -> AsyncGenerator[UserMessageEvent, None]:
    """
    Handles a user message by sending it to the LLM and yielding events.

    Args:
        message (str): The user's message.
        stream (bool): Whether to stream responses.

    Yields:
        UserMessageEvent: Events from the LLM.
    """
    # Append the new user message to the session history
    _message_history.append({'role': 'user', 'content': message})
    try:
        async for content in run_tool_call_loop(
            messages=_message_history,
            tools=computron.tools,
            model=computron.model,
            model_options=computron.options
        ):
            if content is not None:
                yield UserMessageEvent(
                    message=content,
                    final=False
                )
    except Exception as exc:
        logger.exception(f"Error handling user message: {exc}")
        yield UserMessageEvent(message="An error occurred while processing your message.", final=True)

async def run_tool_call_loop(
    messages: list[dict[str, str]],
    tools: list[Callable[..., object]],
    model: str = '',
    model_options: Mapping[str, Any] | None = None
) -> AsyncGenerator[str, None]:
    """
    Executes a chat loop with the LLM, handling tool calls and yielding message content.
    This function mutates the messages list in place by appending assistant and tool messages.

    Args:
        messages (list[dict[str, str]]): The chat history (including system message). This list is mutated in place.
        tools (list[Callable[..., object]]): List of tool functions to use for tool calls.
        model (str): The model name to use for the LLM.
        model_options (Mapping[str, Any] | None): Options to pass to the LLM.

    Yields:
        str: The message content at each step (never tool call results directly).
    """
    opts = dict(model_options) if model_options else {}
    client = AsyncClient()
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