"""Common models for agent message streaming and agent configuration."""

import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Agent(BaseModel):
    """Represents the configuration for a generic agent.

    Args:
        name (str): The agent's name.
        description (str): Description of the agent.
        instruction (str): The root prompt or instruction for the agent.
        model (str): The model name to use.
        options (Dict[str, Any]): Model options (e.g., num_ctx).
        tools (List[Callable[..., Any]]): List of callable tools available to the agent.
        think (bool): Whether or not the model should think. Not all models support thinking.

    """

    name: str
    description: str
    instruction: str
    model: str
    options: dict[str, Any]
    tools: list[Callable[..., Any]]
    think: bool = False


class UserMessageEvent(BaseModel):
    """Represents a message event from the agent.

    Attributes:
        message (str): The message content from the agent.
        final (bool): Whether this is the final response in the sequence.
        thinking (Optional[str]): The agent's internal reasoning or thought process, if available.

    """

    message: str
    final: bool
    thinking: str | None = None


class Data(BaseModel):
    """Represents binary or non-text data sent with a user message.

    Attributes:
        base64_encoded (str): The base64-encoded data payload.
        content_type (str): The MIME type of the data (e.g., 'image/png').

    """

    base64_encoded: str
    content_type: str
