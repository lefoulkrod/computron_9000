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
from agents.ollama.sdk import run_tool_call_loop

logger = logging.getLogger(__name__)

config = load_config()

# Module-level message history for chat session, initialized with system message
_message_history: list[dict[str, str]] = [
    {'role': 'system', 'content': computron.instruction}
]

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