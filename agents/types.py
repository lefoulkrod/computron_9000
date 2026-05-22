"""Common models for agent message streaming and agent configuration."""

import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


__all__ = [
    "Agent",
    "Data",
]


class Agent(BaseModel):
    """Represents the configuration for a generic agent.

    Attributes:
        name: The agent's name.
        description: Description of the agent.
        instruction: The root prompt or instruction for the agent.
        model: The model name to use.
        options: Model options passed to the provider (temperature, top_p, etc.).
        tools: List of callable tools available to the agent.
        think: Whether the model should think. Not all models support thinking.
        context_window: Model's context window in tokens, used as the compaction denominator.
        compaction_threshold: Fill ratio (0.0–1.0) at which compaction fires.
        max_iterations: Maximum tool-call loop iterations before forced stop.
    """

    name: str
    description: str
    instruction: str
    provider: str
    model: str
    options: dict[str, Any]
    tools: list[Callable[..., Any]]
    think: bool = False
    context_window: int = 0
    compaction_threshold: float = 0.75
    max_iterations: int = 0


class Data(BaseModel):
    """Represents binary or non-text data sent with a user message.

    Attributes:
        base64_encoded: The base64-encoded data payload.
        content_type: The MIME type of the data (e.g., 'image/png').
        filename: Original filename from the browser upload, if available.
    """

    base64_encoded: str
    content_type: str
    filename: str | None = None
