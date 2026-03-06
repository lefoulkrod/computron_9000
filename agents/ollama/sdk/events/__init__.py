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
    StopRequestedError,
    agent_span,
    check_stop,
    event_context,
    get_model_options,
    publish_event,
    request_stop,
    set_model_options,
)
from .dispatcher import EventDispatcher, Handler
from .models import (
    AssistantEventPayload,
    AssistantResponse,
    AssistantResponseData,
    BrowserScreenshotPayload,
    GenerationPreviewPayload,
    TerminalOutputPayload,
    ToolCallPayload,
)

__all__ = [
    "AssistantEventPayload",
    "AssistantResponse",
    "AssistantResponseData",
    "BrowserScreenshotPayload",
    "EventDispatcher",
    "GenerationPreviewPayload",
    "Handler",
    "StopRequestedError",
    "TerminalOutputPayload",
    "ToolCallPayload",
    "agent_span",
    "check_stop",
    "event_context",
    "get_model_options",
    "publish_event",
    "request_stop",
    "set_model_options",
]
