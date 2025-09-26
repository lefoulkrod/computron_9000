"""Common models for agent message streaming and agent configuration."""

import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from agents.ollama.sdk.events import AssistantEventPayload, AssistantResponseData

logger = logging.getLogger(__name__)


__all__ = [
    "Agent",
    "Data",
    "UserMessageEvent",
]


class Agent(BaseModel):
    """Represents the configuration for a generic agent.

    Attributes:
        name: The agent's name.
        description: Description of the agent.
        instruction: The root prompt or instruction for the agent.
        model: The model name to use.
        options: Model options (e.g., num_ctx).
        tools: List of callable tools available to the agent.
        think: Whether the model should think. Not all models support thinking.
    """

    name: str
    description: str
    instruction: str
    model: str
    options: dict[str, Any]
    tools: list[Callable[..., Any]]
    think: bool = False


class UserMessageEvent(BaseModel):
    """Represents a message event from an agent.

    Attributes:
        message: The message content from the agent.
        final: Whether this is the final response in the sequence.
        thinking: The agent's internal reasoning or thought process, if available.
        content: Alias for message to align with the new event envelope.
        data: Optional list of auxiliary payloads attached to the response.
        event: Optional structured event payload (e.g., tool call metadata).
    """

    message: str
    final: bool
    thinking: str | None = None
    # New, backward-compatible fields for richer events
    content: str | None = None
    data: list[AssistantResponseData] | None = None  # type: ignore[type-arg]
    event: AssistantEventPayload | None = None  # type: ignore[type-arg]


class Data(BaseModel):
    """Represents binary or non-text data sent with a user message.

    Attributes:
        base64_encoded: The base64-encoded data payload.
        content_type: The MIME type of the data (e.g., 'image/png').
    """

    base64_encoded: str
    content_type: str
