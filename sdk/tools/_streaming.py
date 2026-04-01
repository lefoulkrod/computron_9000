"""Streaming utilities for tool execution progress and real-time output.

This module provides utilities for tools to report progress updates and stream
output in real-time to the event system. This enables better UX for long-running
tool operations.

Example usage:
    ```python
    async def long_running_tool(query: str, progress: ProgressTracker | None = None) -> Result:
        if progress:
            progress.start("Initializing...")
        
        step1 = await do_step1()
        if progress:
            progress.update(30, "Step 1 complete")
        
        step2 = await do_step2()
        if progress:
            progress.update(60, "Step 2 complete")
        
        result = await finalize()
        if progress:
            progress.complete("Done!")
        
        return result
    ```
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Protocol

from sdk.events import AgentEvent, ToolProgressPayload, ToolStreamPayload, publish_event

logger = logging.getLogger(__name__)


class ProgressReporter(Protocol):
    """Protocol for progress reporting.
    
    Tools can accept any object implementing this protocol to report progress
    without depending on specific implementations.
    """
    
    def start(self, message: str | None = None, stage: str | None = None) -> None:
        """Mark the operation as started."""
        ...
    
    def update(self, progress: int, message: str | None = None, stage: str | None = None) -> None:
        """Update progress percentage and optional message."""
        ...
    
    def complete(self, message: str | None = None) -> None:
        """Mark the operation as complete (100%)."""
        ...
    
    def fail(self, message: str) -> None:
        """Mark the operation as failed."""
        ...


class ProgressTracker:
    """Tracks and publishes progress events for tool execution.
    
    This class provides a simple way for tools to report progress that gets
    automatically published as ToolProgressPayload events.
    
    Attributes:
        tool_name: Name of the tool being executed.
        tool_call_id: Unique identifier for this tool invocation.
        _current_progress: Current progress percentage (0-100).
        _current_stage: Current execution stage.
    
    Example:
        ```python
        tracker = ProgressTracker("my_tool")
        tracker.start("Starting operation...")
        
        for i, item in enumerate(items):
            process(item)
            tracker.update(
                progress=int((i + 1) / len(items) * 100),
                message=f"Processed {i + 1}/{len(items)} items"
            )
        
        tracker.complete("Operation completed successfully")
        ```
    """
    
    def __init__(
        self,
        tool_name: str,
        tool_call_id: str | None = None,
    ) -> None:
        """Initialize the progress tracker.
        
        Args:
            tool_name: Name of the tool being executed.
            tool_call_id: Optional unique identifier. If not provided, one
                will be generated automatically.
        """
        self.tool_name = tool_name
        self.tool_call_id = tool_call_id or uuid.uuid4().hex
        self._current_progress = 0
        self._current_stage: str | None = None
        self._metadata: dict[str, Any] = {}
    
    def start(self, message: str | None = None, stage: str = "starting") -> None:
        """Mark the operation as started.
        
        Args:
            message: Optional status message.
            stage: Current execution stage (default: "starting").
        """
        self._current_progress = 0
        self._current_stage = stage
        self._publish(message)
    
    def update(
        self,
        progress: int,
        message: str | None = None,
        stage: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Update progress and optionally change stage.
        
        Args:
            progress: Percentage complete (0-100).
            message: Optional status message.
            stage: Optional new execution stage.
            metadata: Optional additional metadata to include.
        """
        # Clamp progress to valid range
        self._current_progress = max(0, min(100, progress))
        if stage:
            self._current_stage = stage
        if metadata:
            self._metadata.update(metadata)
        self._publish(message)
    
    def complete(self, message: str | None = "Complete") -> None:
        """Mark the operation as complete.
        
        Args:
            message: Completion message (default: "Complete").
        """
        self._current_progress = 100
        self._current_stage = "completed"
        self._publish(message)
    
    def fail(self, message: str) -> None:
        """Mark the operation as failed.
        
        Args:
            message: Error message describing the failure.
        """
        self._current_stage = "failed"
        self._publish(message)
    
    def set_metadata(self, key: str, value: Any) -> None:
        """Set metadata key-value pair.
        
        Args:
            key: Metadata key.
            value: Metadata value (must be JSON serializable).
        """
        self._metadata[key] = value
    
    def _publish(self, message: str | None = None) -> None:
        """Publish a progress event.
        
        Args:
            message: Optional status message.
        """
        try:
            event = AgentEvent(
                payload=ToolProgressPayload(
                    type="tool_progress",
                    tool_name=self.tool_name,
                    tool_call_id=self.tool_call_id,
                    progress=self._current_progress if self._current_progress > 0 else None,
                    message=message,
                    stage=self._current_stage,
                    metadata=self._metadata if self._metadata else None,
                )
            )
            publish_event(event)
        except Exception as exc:
            # Log but don't raise - progress reporting should not fail the tool
            logger.warning("Failed to publish progress event: %s", exc)


class StreamingContext:
    """Context manager for streaming tool output.
    
    Provides a convenient way to stream output chunks from tools
    while automatically handling the tool_call_id and event publishing.
    
    Example:
        ```python
        async def stream_command(cmd: str) -> None:
            with StreamingContext("run_bash_cmd") as stream:
                async for line in execute_streaming(cmd):
                    stream.write(line)
        ```
    """
    
    def __init__(
        self,
        tool_name: str,
        tool_call_id: str | None = None,
    ) -> None:
        """Initialize the streaming context.
        
        Args:
            tool_name: Name of the tool being executed.
            tool_call_id: Optional unique identifier. If not provided, one
                will be generated automatically.
        """
        self.tool_name = tool_name
        self.tool_call_id = tool_call_id or uuid.uuid4().hex
    
    def __enter__(self) -> StreamingContext:
        """Enter the context (no-op, returns self for chaining)."""
        return self
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the context (no cleanup needed)."""
        pass
    
    def write(self, chunk: str, is_stderr: bool = False) -> None:
        """Write a chunk of output.
        
        Args:
            chunk: Output text chunk.
            is_stderr: Whether this chunk is from stderr (default: False).
        """
        try:
            event = AgentEvent(
                payload=ToolStreamPayload(
                    type="tool_stream",
                    tool_name=self.tool_name,
                    tool_call_id=self.tool_call_id,
                    chunk=chunk,
                    is_stderr=is_stderr,
                )
            )
            publish_event(event)
        except Exception as exc:
            # Log but don't raise - streaming should not fail the tool
            logger.warning("Failed to publish stream event: %s", exc)
    
    def write_stdout(self, chunk: str) -> None:
        """Write a stdout chunk.
        
        Args:
            chunk: Output text chunk from stdout.
        """
        self.write(chunk, is_stderr=False)
    
    def write_stderr(self, chunk: str) -> None:
        """Write a stderr chunk.
        
        Args:
            chunk: Output text chunk from stderr.
        """
        self.write(chunk, is_stderr=True)


def emit_tool_progress(
    tool_name: str,
    tool_call_id: str,
    progress: int | None = None,
    message: str | None = None,
    stage: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Emit a single tool progress event.
    
    This is a convenience function for tools that don't need the full
    ProgressTracker lifecycle and just want to emit a one-off event.
    
    Args:
        tool_name: Name of the tool.
        tool_call_id: Unique identifier for this invocation.
        progress: Percentage complete (0-100), or None for indeterminate.
        message: Optional status message.
        stage: Optional execution stage.
        metadata: Optional additional metadata.
    """
    try:
        event = AgentEvent(
            payload=ToolProgressPayload(
                type="tool_progress",
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                progress=progress,
                message=message,
                stage=stage,
                metadata=metadata,
            )
        )
        publish_event(event)
    except Exception as exc:
        logger.warning("Failed to emit tool progress event: %s", exc)


def emit_tool_stream(
    tool_name: str,
    tool_call_id: str,
    chunk: str,
    is_stderr: bool = False,
) -> None:
    """Emit a single tool stream event.
    
    This is a convenience function for emitting streaming output chunks.
    
    Args:
        tool_name: Name of the tool.
        tool_call_id: Unique identifier for this invocation.
        chunk: Output text chunk.
        is_stderr: Whether this chunk is from stderr.
    """
    try:
        event = AgentEvent(
            payload=ToolStreamPayload(
                type="tool_stream",
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                chunk=chunk,
                is_stderr=is_stderr,
            )
        )
        publish_event(event)
    except Exception as exc:
        logger.warning("Failed to emit tool stream event: %s", exc)


__all__ = [
    "ProgressReporter",
    "ProgressTracker",
    "StreamingContext",
    "emit_tool_progress",
    "emit_tool_stream",
]
