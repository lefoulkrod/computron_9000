"""Public exports for the events package.

This package provides:
- Event models (AssistantResponse, ToolCallPayload, etc.)
- Context utilities for publishing events without plumbing dispatcher handles
    through every call site. Low-level helpers like ``publish_event`` and
    ``agent_span`` are available for emission and attribution inside a turn scope.

Turn lifecycle management (``turn_scope``, stop signaling, nudge queues) lives
in ``agents.ollama.sdk.turn``.
"""

from .context import (
    agent_span,
    get_model_options,
    publish_event,
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
    "TerminalOutputPayload",
    "ToolCallPayload",
    "agent_span",
    "get_model_options",
    "publish_event",
    "set_model_options",
]
