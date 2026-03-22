"""Public exports for the events package.

This package provides:
- Event models (AssistantResponse, ToolCallPayload, etc.)
- Context utilities for publishing events without plumbing dispatcher handles
    through every call site. Low-level helpers like ``publish_event`` and
    ``agent_span`` are available for emission and attribution inside a turn scope.

Turn lifecycle management (``turn_scope``, stop signaling, nudge queues) lives
in ``sdk.turn``.
"""

from ._context import (
    agent_span,
    collect_sub_agent_history,
    get_current_agent_name,
    get_model_options,
    get_sub_agent_histories,
    init_sub_agent_collector,
    publish_event,
    set_model_options,
)
from ._dispatcher import EventDispatcher, Handler
from ._models import (
    AssistantEventPayload,
    AssistantResponse,
    AssistantResponseData,
    AudioPlaybackPayload,
    BrowserScreenshotPayload,
    ContextUsagePayload,
    DesktopActivePayload,
    FileOutputPayload,
    GenerationPreviewPayload,
    SkillAppliedPayload,
    TerminalOutputPayload,
    ToolCallPayload,
    ToolCreatedPayload,
)

__all__ = [
    "AssistantEventPayload",
    "AssistantResponse",
    "AssistantResponseData",
    "AudioPlaybackPayload",
    "BrowserScreenshotPayload",
    "ContextUsagePayload",
    "DesktopActivePayload",
    "EventDispatcher",
    "FileOutputPayload",
    "GenerationPreviewPayload",
    "Handler",
    "SkillAppliedPayload",
    "TerminalOutputPayload",
    "ToolCallPayload",
    "ToolCreatedPayload",
    "agent_span",
    "collect_sub_agent_history",
    "get_current_agent_name",
    "get_model_options",
    "get_sub_agent_histories",
    "init_sub_agent_collector",
    "publish_event",
    "set_model_options",
]
