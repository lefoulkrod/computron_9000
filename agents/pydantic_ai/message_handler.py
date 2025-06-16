"""Message handler for the Pydantic AI agent framework (multi-agent, async)."""

import logging
from typing import Any, AsyncGenerator, List

from agents.types import UserMessageEvent
from agents.pydantic_ai.computron import run_computron_agent
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage

DEFAULT_USER_ID = "default_user"
DEFAULT_SESSION_ID = "default_session"
APP_NAME = "computron_9000"

# In-memory cache for message history (stores ModelMessage objects)
_message_history: List[ModelMessage] = []

def get_message_history() -> list[ModelMessage]:
    """
    Retrieve the in-memory message history.

    Returns:
        list[ModelMessage]: List of user and agent messages in order.
    """
    return list(_message_history)

async def add_messages_to_history(messages: list[ModelMessage]) -> None:
    """
    Add messages to the in-memory message history.

    Args:
        messages (list[ModelMessage]): The messages to add.
    """
    _message_history.extend(messages)

async def handle_user_message(message: str, stream: bool) -> AsyncGenerator[UserMessageEvent, None]:
    """
    Handles user message with the computron agent, streaming or returning the final response.

    Args:
        message (str): The user message to send to the agent.
        stream (bool): Whether to stream responses (True) or return only the final response (False).

    Yields:
        UserMessageEvent: Contains the message and final flag.
            - If stream=True, yields one event per agent event.
            - If stream=False, yields only the final response event.
    """
    try:
        # Pass the current message history to the agent
        result = await run_computron_agent(message, message_history=get_message_history())
        await add_messages_to_history(result.all_messages())
        yield UserMessageEvent(message=result.output, final=True)
    except Exception as exc:
        logging.error(f"Pydantic AI message handler error: {exc}")
        yield UserMessageEvent(message=f"[Error: {exc}]", final=True)
