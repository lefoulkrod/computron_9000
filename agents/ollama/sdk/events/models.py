"""Event models for assistant responses and tool call notifications.

This module defines the public schema for events emitted by the assistant while
handling a single user message. The schema is intentionally generic and uses a
discriminated union for event payloads so additional event types can be added
without breaking existing consumers.

Design notes:
- Binary payloads are represented as base64-encoded strings paired with a
  content type.
- Event payloads use a discriminator field named "type".
- All top-level fields on AssistantResponse are optional to support partial,
  streaming-style emissions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class AssistantResponseData(BaseModel):
    """Represents a piece of binary or auxiliary data attached to a response.

    Attributes:
        content_type: The MIME type of the data payload (e.g., "image/png").
        content: The base64-encoded content bytes.
    """

    content_type: str
    content: str  # base64 encoded payload


class ToolCallPayload(BaseModel):
    """Metadata for tool invocation notifications.

    Attributes:
        type: Discriminator for the event payload; always "tool_call" for this model.
        name: The name of the tool being invoked.
    """

    type: Literal["tool_call"]
    name: str


# Extend this alias with additional payload models as new event types are introduced.
AssistantEventPayload = Annotated[ToolCallPayload, Field(discriminator="type")]


class AssistantResponse(BaseModel):
    """Top-level event envelope emitted during message handling.

    The envelope supports partial updates for streaming by making all fields optional.

    Attributes:
        content: Natural-language content produced by the model, if any.
        thinking: Optional chain-of-thought or rationale text, if available.
        data: Optional list of binary or auxiliary payloads associated with this response.
        event: Optional structured event metadata (e.g., tool call notifications).
        timestamp: UTC timestamp when the event instance was created.
    """

    content: str | None = None
    thinking: str | None = None
    data: list[AssistantResponseData] = Field(default_factory=list)
    event: AssistantEventPayload | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    final: bool | None = None


class DispatchEvent(BaseModel):
    """Envelope emitted by the dispatcher with context metadata."""

    context_id: str
    parent_context_id: str | None = None
    depth: int
    payload: AssistantResponse


__all__ = [
    "AssistantEventPayload",
    "DispatchEvent",
    "AssistantResponse",
    "AssistantResponseData",
    "ToolCallPayload",
]
