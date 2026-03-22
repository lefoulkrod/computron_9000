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


class BrowserScreenshotPayload(BaseModel):
    """Metadata for browser screenshot events.

    Attributes:
        type: Discriminator for the event payload; always "browser_screenshot" for this model.
        url: The current URL of the browser page.
        title: The page title.
        screenshot: Base64-encoded PNG screenshot of the viewport.
    """

    type: Literal["browser_screenshot"]
    url: str
    title: str
    screenshot: str  # base64 encoded PNG


class FileOutputPayload(BaseModel):
    """Metadata for file output events.

    Attributes:
        type: Discriminator for the event payload; always "file_output" for this model.
        filename: The name of the file (basename for display/download).
        content_type: The MIME type of the file (e.g., "text/csv", "image/png").
        content: Base64-encoded file content (legacy, prefer ``path``).
        path: Absolute container path served by the file route.
    """

    type: Literal["file_output"]
    filename: str
    content_type: str
    content: str | None = None
    path: str | None = None


class ToolCreatedPayload(BaseModel):
    """Emitted when a new custom tool is successfully created.

    Attributes:
        type: Discriminator; always "tool_created".
        name: The name of the newly created tool.
    """

    type: Literal["tool_created"]
    name: str


class AudioPlaybackPayload(BaseModel):
    """Emitted when the agent wants to play audio directly in the browser.

    Attributes:
        type: Discriminator; always "audio_playback".
        content_type: MIME type of the audio (e.g. "audio/mpeg").
        content: Base64-encoded audio content.
    """

    type: Literal["audio_playback"]
    content_type: str
    content: str  # base64 encoded


class TerminalOutputPayload(BaseModel):
    """Emitted when a bash command starts or completes in the virtual computer.

    Two events are published per command: one with ``status="running"`` before
    execution begins (carrying only the command text), and one with
    ``status="completed"`` after execution finishes (carrying output and exit
    code).  Both share the same ``cmd_id`` so the frontend can correlate them.

    Attributes:
        type: Discriminator; always "terminal_output".
        cmd_id: Unique identifier linking the running/completed pair.
        cmd: The command that was executed.
        status: Either "running" or "completed".
        stdout: Standard output text, if any.
        stderr: Standard error text, if any.
        exit_code: Exit code of the command, if available.
    """

    type: Literal["terminal_output"]
    cmd_id: str
    cmd: str
    status: Literal["running", "streaming", "completed"] = "completed"
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None


class SkillAppliedPayload(BaseModel):
    """Emitted when a skill is applied during a conversation.

    Attributes:
        type: Discriminator; always "skill_applied".
        skill_name: The name of the skill being applied.
    """

    type: Literal["skill_applied"]
    skill_name: str


class DesktopActivePayload(BaseModel):
    """Emitted when the desktop environment starts to signal the UI.

    Attributes:
        type: Discriminator; always "desktop_active".
        resolution: Desktop resolution string (e.g. "1280x720").
    """

    type: Literal["desktop_active"]
    resolution: str


class ContextUsagePayload(BaseModel):
    """Emitted after each LLM call with current context window usage.

    Attributes:
        type: Discriminator; always "context_usage".
        context_used: Prompt + completion tokens consumed on the last call.
        context_limit: The model's context window size.
        fill_ratio: Fraction of the context window consumed (0.0–1.0+).
    """

    type: Literal["context_usage"]
    context_used: int
    context_limit: int
    fill_ratio: float
    iteration: int | None = None
    max_iterations: int | None = None


class GenerationPreviewPayload(BaseModel):
    """Emitted during image/video generation to stream progress and previews.

    Multiple events share the same ``gen_id`` to track a single generation.
    For images, ``preview`` contains a TAESD-decoded JPEG at each step.
    For video, ``preview`` is sent periodically (first frame only).
    On completion, ``output`` contains the base64-encoded final file.

    Attributes:
        type: Discriminator; always "generation_preview".
        gen_id: Unique identifier correlating progress events.
        media_type: Either "image" or "video".
        status: Current generation phase.
        step: Current inference step number.
        total_steps: Total inference steps.
        preview: Base64-encoded JPEG preview image.
        message: Human-readable status text.
        output: Base64-encoded final file on completion.
        output_content_type: MIME type of the final output.
    """

    type: Literal["generation_preview"]
    gen_id: str
    media_type: str
    status: Literal["loading", "generating", "complete", "failed"]
    step: int | None = None
    total_steps: int | None = None
    preview: str | None = None
    message: str | None = None
    output: str | None = None
    output_content_type: str | None = None
    output_path: str | None = None


class AgentStartedPayload(BaseModel):
    """Emitted when an agent begins execution.

    Attributes:
        type: Discriminator; always "agent_started".
        agent_id: Hierarchical context id for this agent instance.
        agent_name: Human-readable agent name.
        parent_agent_id: Context id of the parent agent, or None for root.
        instruction: The instruction or user message this agent was given.
    """

    type: Literal["agent_started"]
    agent_id: str
    agent_name: str
    parent_agent_id: str | None = None
    instruction: str | None = None


class AgentCompletedPayload(BaseModel):
    """Emitted when an agent finishes execution.

    Attributes:
        type: Discriminator; always "agent_completed".
        agent_id: Hierarchical context id for this agent instance.
        agent_name: Human-readable agent name.
        status: How the agent finished — success, error, or stopped.
    """

    type: Literal["agent_completed"]
    agent_id: str
    agent_name: str
    status: Literal["success", "error", "stopped"]


# Extend this alias with additional payload models as new event types are introduced.
AssistantEventPayload = Annotated[
    ToolCallPayload
    | BrowserScreenshotPayload
    | FileOutputPayload
    | ToolCreatedPayload
    | AudioPlaybackPayload
    | TerminalOutputPayload
    | GenerationPreviewPayload
    | ContextUsagePayload
    | SkillAppliedPayload
    | DesktopActivePayload
    | AgentStartedPayload
    | AgentCompletedPayload,
    Field(discriminator="type"),
]


class AssistantResponse(BaseModel):
    """Top-level event envelope emitted during message handling.

    The envelope supports partial updates for streaming by making all fields optional.

    Attributes:
        content: Natural-language content produced by the model, if any.
        thinking: Optional chain-of-thought or rationale text, if available.
        data: Optional list of binary or auxiliary payloads associated with this response.
        event: Optional structured event metadata (e.g., tool call notifications).
        timestamp: UTC timestamp when the event instance was created.
        agent_name: Optional human-readable agent name for attribution (e.g., "Browser Agent").
        depth: Optional nesting depth (0 = main agent, 1+ = sub-agents).
    """

    content: str | None = None
    thinking: str | None = None
    data: list[AssistantResponseData] = Field(default_factory=list)
    event: AssistantEventPayload | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    # Final is a boolean flag indicating terminal/complete event. Default to
    # False so consumers can rely on a boolean value instead of None.
    final: bool = False
    # When True, content/thinking are incremental token deltas to append.
    # When None (default, excluded from JSON), they are complete chunks.
    delta: bool | None = None
    # Agent attribution metadata for UI rendering
    agent_name: str | None = None
    depth: int | None = None
    agent_id: str | None = None


__all__ = [
    "AgentCompletedPayload",
    "AgentStartedPayload",
    "AssistantEventPayload",
    "AssistantResponse",
    "AssistantResponseData",
    "AudioPlaybackPayload",
    "BrowserScreenshotPayload",
    "ContextUsagePayload",
    "DesktopActivePayload",
    "FileOutputPayload",
    "GenerationPreviewPayload",
    "SkillAppliedPayload",
    "TerminalOutputPayload",
    "ToolCallPayload",
    "ToolCreatedPayload",
]
