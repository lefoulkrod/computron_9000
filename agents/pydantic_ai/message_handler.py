"""Message handler for the Pydantic AI agent framework (multi-agent, async)."""

import base64
import logging
from typing import AsyncGenerator, List, Sequence

from agents.types import UserMessageEvent, Data
from agents.pydantic_ai.computron import run_computron_agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.messages import ModelMessage
from pydantic_ai.messages import BinaryContent
from pydantic_ai import Agent

DEFAULT_USER_ID = "default_user"
DEFAULT_SESSION_ID = "default_session"
APP_NAME = "computron_9000"

# In-memory cache for message history (stores ModelMessage objects)
_message_history: List[ModelMessage] = []

logger = logging.getLogger(__name__)

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
    logger.debug(f"Current history size: {len(_message_history)}")
    logger.debug(f"Adding {len(messages)} messages to history")
    _message_history.extend(messages)

async def handle_user_message(message: str, data: Sequence[Data] | None = None) -> AsyncGenerator[UserMessageEvent, None]:
    """
    Handles user message with the computron agent, streaming or returning the final response.

    Args:
        message (str): The user message to send to the agent.
        data (Sequence[Data] | None): Optional list of base64-encoded data and content type objects.

    Yields:
        UserMessageEvent: Contains the message and final flag.
            - If stream=True, yields one event per agent event.
            - If stream=False, yields only the final response event.
    """
    try:
        # If data contains exactly one entry, decode and make direct agent call
        if data and len(data) == 1:
            entry = data[0]
            try:
                ollama_model = OpenAIModel(
                    model_name='gemma3:12b',
                    provider=OpenAIProvider(
                        base_url="http://localhost:11434/v1",
                    ),
                    system_prompt_role="system",
)
                binary_content = base64.b64decode(entry.base64_encoded)
                logger.debug(f"Decoded binary content of length {len(binary_content)} with content type {entry.content_type}")
                agent = Agent(model=ollama_model)
                result = await agent.run(
                [
                    message,
                    BinaryContent(data=binary_content, media_type=entry.content_type),  
                ],  
)
                yield UserMessageEvent(message=result.output, final=True)
                return
            except Exception as decode_exc:
                logger.error(f"Failed to decode base64 data or make direct agent call: {decode_exc}")
                yield UserMessageEvent(message=f"[Error decoding data or agent call: {decode_exc}]", final=True)
                return
        # Pass the current message history to the agent
        result = await run_computron_agent(message, message_history=get_message_history())
        if result is None:
            raise RuntimeError("COMPUTRON_9000 agent returned None result.")
        logger.debug(f"COMPUTRON_9000 usage: {result.usage()}")
        await add_messages_to_history(result.new_messages())
        yield UserMessageEvent(message=result.output, final=True)
    except Exception as exc:
        logger.error(f"Pydantic AI message handler error: {exc}")
        yield UserMessageEvent(message=f"[Error: {exc}]", final=True)
