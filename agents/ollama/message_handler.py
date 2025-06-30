import json
import logging
from typing import AsyncGenerator, Sequence, AsyncIterator, Iterator, Optional, Union, Tuple

from ollama import AsyncClient, ChatResponse

from agents.types import UserMessageEvent, Data
from config import load_config
from .agents import computron

logger = logging.getLogger(__name__)

config = load_config()

async def handle_user_message(
    message: str,
    data: Sequence[Data] | None = None,
    stream: bool = False
) -> AsyncGenerator[UserMessageEvent, None]:
    """
    Handles a user message by sending it to the LLM and yielding events.

    Args:
        message (str): The user's message.
        data (Sequence[Data] | None): Optional additional data.
        stream (bool): Whether to stream responses.

    Yields:
        UserMessageEvent: Events from the LLM.
    """
    try:
        async for content in run_as_agent(message, data):
            if content is not None:
                yield UserMessageEvent(
                    message=content,
                    final=False
                )
    except Exception as exc:
        logger.exception(f"Error handling user message: {exc}")
        yield UserMessageEvent(message="An error occurred while processing your message.", final=True)

async def run_as_agent_stream(iterator: AsyncIterator[ChatResponse]) -> AsyncIterator[Tuple[Optional[str], bool]]:
    """
    Consumes an async iterator of ChatResponse and yields a tuple of (message content, done flag) as they are returned.

    Args:
        iterator (AsyncIterator[ChatResponse]): An async iterator yielding ChatResponse objects.

    Yields:
        Tuple[Optional[str], bool]: The message content from each ChatResponse object (or None) and the done flag.

    Raises:
        Exception: If an error occurs during iteration.
    """
    try:
        async for response in iterator:
            content = response.message.content
            done = response.done or False
            yield content, done
    except Exception as exc:
        logger.exception(f"Error running agent iterator: {exc}")
        raise

async def run_as_agent(
    message: str,
    data: Sequence[Data] | None = None
) -> AsyncGenerator[str, None]:
    """
    Handles a user message, invokes the LLM, executes tool calls, and yields message content at each step.

    Args:
        message (str): The user's message.
        data (Sequence[Data] | None): Optional additional data.

    Yields:
        str: The message content at each step (never tool call results directly).
    """
    system_message = {'role': 'system', 'content': computron.instruction}
    user_message = {'role': 'user', 'content': message}
    chat_history = [system_message, user_message]
    client = AsyncClient()
    while True:
        try:
            response = await client.chat(
                model=computron.model,
                messages=chat_history,
                options={
                    "num_ctx": computron.options["num_ctx"],
                },
                tools=computron.tools,
                stream=False,
            )
            logger.debug(f"LLM response: {response}")
            content = response.message.content or ""
            tool_calls = getattr(response.message, 'tool_calls', None)
            if content.strip():
                yield content
            if not tool_calls:
                break
            for tool_call in tool_calls:
                function = getattr(tool_call, 'function', None)
                if not function:
                    logger.warning(f"Tool call missing function: {tool_call}")
                    continue
                tool_name = getattr(function, 'name', None)
                arguments = getattr(function, 'arguments', {})
                tool_func = None
                for tool in computron.tools:
                    if hasattr(tool, '__name__') and tool.__name__ == tool_name:
                        tool_func = tool
                        break
                if not tool_func:
                    logger.error(f"Tool '{tool_name}' not found in computron.tools.")
                    tool_result = {"tool": tool_name, "error": "Tool not found"}
                else:
                    try:
                        result = tool_func(**arguments)
                        if hasattr(result, 'dict'):
                            result = result.dict()
                        tool_result = {"tool": tool_name, "result": result}
                    except Exception as exc:
                        logger.exception(f"Error running tool '{tool_name}': {exc}")
                        tool_result = {"tool": tool_name, "error": str(exc)}
                tool_message = {
                    'role': 'tool',
                    'name': tool_name,
                    'content': json.dumps(tool_result)
                }
                chat_history.append(tool_message)
            # Do not yield tool results, just continue looping
        except Exception as exc:
            logger.exception(f"Error in run_as_agent: {exc}")
            yield "An error occurred while processing your message."
            break