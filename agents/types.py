"""Common models for agent message streaming and agent configuration."""

import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


__all__ = [
    "Agent",
    "Data",
    "LLMOptions",
]


class LLMOptions(BaseModel):
    """User-facing LLM inference options sent from the UI per turn.

    All fields are optional. Only fields that are explicitly set (non-None) are
    forwarded to the model; unset fields let the LLM use its own defaults.

    Attributes:
        model: Model identifier string.
        think: Enable extended thinking/reasoning if supported by the model.
        num_ctx: Context window size in tokens.
        num_predict: Maximum number of tokens to generate (-1 for unlimited).
        temperature: Sampling temperature (0.0-2.0).
        top_k: Top-K sampling cutoff.
        top_p: Nucleus sampling probability threshold.
        repeat_penalty: Penalty applied to repeated tokens.
        reasoning_effort: Reasoning effort level (``low``, ``medium``, ``high``).
        persist_thinking: Whether to store thinking in conversation history.
    """

    model: str | None = None
    think: bool | None = None
    num_ctx: int | None = None
    num_predict: int | None = None
    temperature: float | None = None
    top_k: int | None = None
    top_p: float | None = None
    repeat_penalty: float | None = None
    reasoning_effort: str | None = None
    max_iterations: int | None = None
    persist_thinking: bool | None = None

    def to_ollama_options(self) -> dict[str, Any]:
        """Build an ollama options dict containing only explicitly set values."""
        mapping: dict[str, Any] = {
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
            "temperature": self.temperature,
            "top_k": self.top_k,
            "top_p": self.top_p,
            "repeat_penalty": self.repeat_penalty,
            "reasoning_effort": self.reasoning_effort,
        }
        return {k: v for k, v in mapping.items() if v is not None}


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
        persist_thinking: Whether to store thinking in conversation history.
        max_iterations: Maximum tool-call loop iterations before forced stop.
    """

    name: str
    description: str
    instruction: str
    model: str
    options: dict[str, Any]
    tools: list[Callable[..., Any]]
    think: bool = False
    persist_thinking: bool = True
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
