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
    current_context_depth,
    current_context_id,
    current_parent_context_id,
    event_context,
    get_current_dispatcher,
    make_child_context_id,
    publish_event,
    reset_context_id,
    reset_current_dispatcher,
    set_current_dispatcher,
    use_context_id,
)
from .dispatcher import EventDispatcher, Handler
from .models import (
    AssistantEventPayload,
    AssistantResponse,
    AssistantResponseData,
    BrowserSnapshotPayload,
    DispatchEvent,
    ToolCallPayload,
)

__all__ = [
    "AssistantEventPayload",
    "AssistantResponse",
    "AssistantResponseData",
    "BrowserSnapshotPayload",
    "DispatchEvent",
    "EventDispatcher",
    "Handler",
    "ToolCallPayload",
    "current_context_depth",
    "current_context_id",
    "current_parent_context_id",
    "event_context",
    "get_current_dispatcher",
    "make_child_context_id",
    "publish_event",
    "reset_context_id",
    "reset_current_dispatcher",
    "set_current_dispatcher",
    "use_context_id",
]
