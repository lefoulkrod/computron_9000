"""Public exports for the events package.

This package provides:
- Event models (AssistantResponse, ToolCallPayload, etc.)
- Context utilities for publishing events without plumbing dispatcher handles
    through every call site. Prefer ``event_context`` as the single mechanism for
    binding a dispatcher in scope; it ensures proper setup/teardown and optional
    subscription of a handler. Low-level helpers like ``publish_event`` remain
    available for emission inside that context.
"""

from .context import (
    agent_span,
    event_context,
    publish_event,
)
from .dispatcher import EventDispatcher, Handler
from .models import (
    AssistantEventPayload,
    AssistantResponse,
    AssistantResponseData,
    BrowserSnapshotPayload,
    ToolCallPayload,
)

__all__ = [
    "AssistantEventPayload",
    "AssistantResponse",
    "AssistantResponseData",
    "BrowserSnapshotPayload",
    "EventDispatcher",
    "Handler",
    "ToolCallPayload",
    "agent_span",
    "event_context",
    "publish_event",
]
