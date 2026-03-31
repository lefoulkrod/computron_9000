"""Public exports for the events package.

This package provides:
- Event models (AgentEvent, ContentPayload, ToolCallPayload, etc.)
- Context utilities for publishing events without plumbing dispatcher handles
    through every call site. Low-level helpers like ``publish_event`` and
    ``agent_span`` are available for emission and attribution inside a turn scope.

Turn lifecycle management (``turn_scope``, stop signaling, nudge queues) lives
in ``sdk.turn``.
"""

from ._context import (
    agent_span,
    get_current_agent_id,
    get_current_agent_name,
    get_current_depth,
    get_current_dispatcher,
    get_model_options,
    publish_event,
    set_model_options,
)
from ._dispatcher import EventDispatcher, EventHandler
from ._models import (
    AgentCompletedPayload,
    AgentEvent,
    AgentEventPayload,
    AgentStartedPayload,
    AudioPlaybackPayload,
    BrowserScreenshotPayload,
    ContentPayload,
    ContextUsagePayload,
    DesktopActivePayload,
    FileOutputPayload,
    GenerationPreviewPayload,
    InterventionPayload,
    LoopDetectedPayload,
    ProgressMetricsPayload,
    TerminalOutputPayload,
    ToolCallPayload,
    ToolCreatedPayload,
    TurnEndPayload,
)

__all__ = [
    "AgentCompletedPayload",
    "AgentEvent",
    "AgentEventPayload",
    "AgentStartedPayload",
    "AudioPlaybackPayload",
    "BrowserScreenshotPayload",
    "ContentPayload",
    "ContextUsagePayload",
    "DesktopActivePayload",
    "EventDispatcher",
    "EventHandler",
    "FileOutputPayload",
    "GenerationPreviewPayload",
    "InterventionPayload",
    "LoopDetectedPayload",
    "ProgressMetricsPayload",
    "TerminalOutputPayload",
    "ToolCallPayload",
    "ToolCreatedPayload",
    "TurnEndPayload",
    "agent_span",
    "get_current_agent_id",
    "get_current_agent_name",
    "get_current_depth",
    "get_current_dispatcher",
    "get_model_options",
    "publish_event",
    "set_model_options",
]
