"""Tool progress event emission helpers.

This module provides utilities for long-running tools to emit progress
and stage events during execution. These events are streamed to the UI
in real-time, giving users visibility into tool operation progress.

Usage:
    from tools._progress import tool_progress_context

    async with tool_progress_context("browser_navigate", "nav-123") as progress:
        progress.set_stage("connecting", "Connecting to server...")
        # ... do work ...
        progress.emit("Loaded 50% of page", output="Partial content...")
        progress.set_stage("extracting", "Extracting content...")
        # ... more work ...

Or for simpler usage:
    from tools._progress import emit_tool_progress, emit_tool_stage

    emit_tool_stage("browser_navigate", "nav-123", "navigating", "Loading page...")
    emit_tool_progress("browser_navigate", "nav-123", "Fetched 100 items", progress_percent=50.0)
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from sdk.events import AgentEvent, ToolProgressPayload, ToolStagePayload, publish_event


def _get_tool_call_id(tool_call_id: str | None) -> str:
    """Generate a unique tool call ID if none provided."""
    return tool_call_id or f"tool-{uuid.uuid4().hex[:12]}"


def emit_tool_progress(
    tool_name: str,
    tool_call_id: str,
    message: str | None = None,
    output: str | None = None,
    progress_percent: float | None = None,
) -> None:
    """Emit a tool progress event.

    Args:
        tool_name: The name of the tool being executed.
        tool_call_id: Unique identifier for this tool invocation.
        message: Human-readable progress message.
        output: Optional incremental output (e.g., stdout chunk).
        progress_percent: Optional completion percentage (0.0-100.0).
    """
    publish_event(
        AgentEvent(
            payload=ToolProgressPayload(
                type="tool_progress",
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                message=message,
                output=output,
                progress_percent=progress_percent,
            )
        )
    )


def emit_tool_stage(
    tool_name: str,
    tool_call_id: str,
    stage: str,
    stage_label: str | None = None,
) -> None:
    """Emit a tool stage transition event.

    Args:
        tool_name: The name of the tool being executed.
        tool_call_id: Unique identifier for this tool invocation.
        stage: Machine-readable stage identifier (e.g., "navigating").
        stage_label: Human-readable stage description.
    """
    publish_event(
        AgentEvent(
            payload=ToolStagePayload(
                type="tool_stage",
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                stage=stage,
                stage_label=stage_label or stage,
            )
        )
    )


class ToolProgressEmitter:
    """Context manager for emitting tool progress events.

    Provides a convenient interface for tools to emit both stage
    transitions and incremental progress updates during execution.

    Example:
        async with ToolProgressEmitter("my_tool") as progress:
            progress.set_stage("initializing", "Setting up...")
            # ... work ...
            progress.emit("50% complete", progress_percent=50.0)
            # ... more work ...
    """

    def __init__(self, tool_name: str, tool_call_id: str | None = None) -> None:
        """Initialize the progress emitter.

        Args:
            tool_name: The name of the tool being executed.
            tool_call_id: Optional unique ID; auto-generated if not provided.
        """
        self.tool_name = tool_name
        self.tool_call_id = _get_tool_call_id(tool_call_id)
        self._current_stage: str | None = None

    def set_stage(self, stage: str, stage_label: str | None = None) -> None:
        """Set the current execution stage.

        Args:
            stage: Machine-readable stage identifier.
            stage_label: Human-readable description (defaults to stage).
        """
        self._current_stage = stage
        emit_tool_stage(self.tool_name, self.tool_call_id, stage, stage_label)

    def emit(
        self,
        message: str | None = None,
        output: str | None = None,
        progress_percent: float | None = None,
    ) -> None:
        """Emit a progress update.

        Args:
            message: Human-readable progress message.
            output: Optional incremental output.
            progress_percent: Optional completion percentage.
        """
        emit_tool_progress(
            self.tool_name,
            self.tool_call_id,
            message=message,
            output=output,
            progress_percent=progress_percent,
        )

    def emit_output(self, output: str) -> None:
        """Emit incremental output without a message.

        Args:
            output: Output chunk to stream.
        """
        emit_tool_progress(self.tool_name, self.tool_call_id, output=output)


@asynccontextmanager
async def tool_progress_context(
    tool_name: str,
    tool_call_id: str | None = None,
) -> AsyncIterator[ToolProgressEmitter]:
    """Async context manager for tool progress emission.

    Automatically emits a "started" stage on entry and a "completed"
    stage on successful exit.

    Example:
        async with tool_progress_context("browser_tool") as progress:
            progress.set_stage("navigating", "Loading page...")
            # ... do navigation ...
            progress.emit("Page loaded", progress_percent=100.0)

    Args:
        tool_name: The name of the tool being executed.
        tool_call_id: Optional unique ID; auto-generated if not provided.

    Yields:
        ToolProgressEmitter: The progress emitter instance.
    """
    emitter = ToolProgressEmitter(tool_name, tool_call_id)
    emitter.set_stage("started", f"Starting {tool_name}...")
    try:
        yield emitter
        emitter.set_stage("completed", f"Completed {tool_name}")
    except Exception as exc:
        emitter.set_stage("failed", f"Failed: {exc}")
        raise


__all__ = [
    "ToolProgressEmitter",
    "emit_tool_progress",
    "emit_tool_stage",
    "tool_progress_context",
]