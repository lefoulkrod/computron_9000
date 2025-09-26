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
    enable_content_suppression,
    event_context,
    get_current_dispatcher,
    publish_event,
    reset_content_suppression,
    reset_current_dispatcher,
    set_current_dispatcher,
    suppress_content_enabled,
)
from .dispatcher import EventDispatcher, Handler
from .models import AssistantEventPayload, AssistantResponse, AssistantResponseData, ToolCallPayload

__all__ = [
    "AssistantEventPayload",
    "AssistantResponse",
    "AssistantResponseData",
    "EventDispatcher",
    "Handler",
    "ToolCallPayload",
    "enable_content_suppression",
    "event_context",
    "get_current_dispatcher",
    "publish_event",
    "reset_content_suppression",
    "reset_current_dispatcher",
    "set_current_dispatcher",
    "suppress_content_enabled",
]
