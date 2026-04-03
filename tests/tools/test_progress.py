"""Tests for the tool progress streaming module.

These tests verify that the tool progress emission helpers correctly
format and publish events through the event system.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from tools._progress import (
    ToolProgressEmitter,
    emit_tool_progress,
    emit_tool_stage,
    tool_progress_context,
)


class TestEmitToolProgress:
    """Tests for emit_tool_progress function."""

    @patch("tools._progress.publish_event")
    def test_emit_basic_progress(self, mock_publish: MagicMock) -> None:
        """Test emitting a basic progress event."""
        emit_tool_progress(
            tool_name="test_tool",
            tool_call_id="call-123",
            message="Processing...",
        )

        assert mock_publish.called
        event = mock_publish.call_args[0][0]
        assert event.payload.type == "tool_progress"
        assert event.payload.tool_call_id == "call-123"
        assert event.payload.tool_name == "test_tool"
        assert event.payload.message == "Processing..."

    @patch("tools._progress.publish_event")
    def test_emit_progress_with_output(self, mock_publish: MagicMock) -> None:
        """Test emitting progress with output chunk."""
        emit_tool_progress(
            tool_name="bash_cmd",
            tool_call_id="call-456",
            message="Line 10 of 100",
            output="stdout chunk here",
            progress_percent=10.0,
        )

        event = mock_publish.call_args[0][0]
        assert event.payload.output == "stdout chunk here"
        assert event.payload.progress_percent == 10.0

    @patch("tools._progress.publish_event")
    def test_emit_progress_with_percent(self, mock_publish: MagicMock) -> None:
        """Test emitting progress with percentage."""
        emit_tool_progress(
            tool_name="browser_tool",
            tool_call_id="call-789",
            progress_percent=50.0,
        )

        event = mock_publish.call_args[0][0]
        assert event.payload.progress_percent == 50.0


class TestEmitToolStage:
    """Tests for emit_tool_stage function."""

    @patch("tools._progress.publish_event")
    def test_emit_stage(self, mock_publish: MagicMock) -> None:
        """Test emitting a stage transition."""
        emit_tool_stage(
            tool_name="test_tool",
            tool_call_id="call-123",
            stage="connecting",
            stage_label="Connecting to server...",
        )

        assert mock_publish.called
        event = mock_publish.call_args[0][0]
        assert event.payload.type == "tool_stage"
        assert event.payload.stage == "connecting"
        assert event.payload.stage_label == "Connecting to server..."

    @patch("tools._progress.publish_event")
    def test_emit_stage_without_label(self, mock_publish: MagicMock) -> None:
        """Test emitting a stage without explicit label."""
        emit_tool_stage(
            tool_name="test_tool",
            tool_call_id="call-123",
            stage="processing",
        )

        event = mock_publish.call_args[0][0]
        assert event.payload.stage == "processing"
        assert event.payload.stage_label == "processing"


class TestToolProgressEmitter:
    """Tests for ToolProgressEmitter class."""

    @patch("tools._progress.publish_event")
    def test_emitter_set_stage(self, mock_publish: MagicMock) -> None:
        """Test setting stage via emitter."""
        emitter = ToolProgressEmitter("my_tool", "call-abc")
        emitter.set_stage("initializing", "Setting up...")

        event = mock_publish.call_args[0][0]
        assert event.payload.type == "tool_stage"
        assert event.payload.stage == "initializing"
        assert event.payload.stage_label == "Setting up..."

    @patch("tools._progress.publish_event")
    def test_emitter_emit_progress(self, mock_publish: MagicMock) -> None:
        """Test emitting progress via emitter."""
        emitter = ToolProgressEmitter("my_tool", "call-abc")
        emitter.emit("Halfway done", progress_percent=50.0)

        event = mock_publish.call_args[0][0]
        assert event.payload.type == "tool_progress"
        assert event.payload.message == "Halfway done"
        assert event.payload.progress_percent == 50.0

    @patch("tools._progress.publish_event")
    def test_emitter_emit_output(self, mock_publish: MagicMock) -> None:
        """Test emitting output via emitter."""
        emitter = ToolProgressEmitter("my_tool", "call-abc")
        emitter.emit_output("some output")

        event = mock_publish.call_args[0][0]
        assert event.payload.output == "some output"

    @patch("tools._progress.publish_event")
    def test_emitter_auto_generates_id(self, mock_publish: MagicMock) -> None:
        """Test that emitter auto-generates tool_call_id if not provided."""
        emitter = ToolProgressEmitter("my_tool")
        assert emitter.tool_call_id.startswith("tool-")
        assert len(emitter.tool_call_id) > 5


class TestToolProgressContext:
    """Tests for tool_progress_context async context manager."""

    @patch("tools._progress.publish_event")
    async def test_context_emits_started_stage(self, mock_publish: MagicMock) -> None:
        """Test that context emits 'started' stage on entry."""
        async with tool_progress_context("my_tool", "call-xyz") as progress:
            pass

        calls = mock_publish.call_args_list
        # First call should be 'started'
        first_event = calls[0][0][0]
        assert first_event.payload.type == "tool_stage"
        assert first_event.payload.stage == "started"

    @patch("tools._progress.publish_event")
    async def test_context_emits_completed_stage(self, mock_publish: MagicMock) -> None:
        """Test that context emits 'completed' stage on successful exit."""
        async with tool_progress_context("my_tool", "call-xyz") as progress:
            pass

        calls = mock_publish.call_args_list
        # Last call should be 'completed'
        last_event = calls[-1][0][0]
        assert last_event.payload.type == "tool_stage"
        assert last_event.payload.stage == "completed"

    @patch("tools._progress.publish_event")
    async def test_context_emits_failed_on_exception(self, mock_publish: MagicMock) -> None:
        """Test that context emits 'failed' stage on exception."""
        with pytest.raises(ValueError, match="Test error"):
            async with tool_progress_context("my_tool", "call-xyz") as progress:
                raise ValueError("Test error")

        calls = mock_publish.call_args_list
        # Find the failed stage
        failed_calls = [c for c in calls if c[0][0].payload.stage == "failed"]
        assert len(failed_calls) == 1

    @patch("tools._progress.publish_event")
    async def test_context_allows_emitting_progress(self, mock_publish: MagicMock) -> None:
        """Test that progress can be emitted within the context."""
        async with tool_progress_context("my_tool", "call-xyz") as progress:
            progress.set_stage("working", "Doing work...")
            progress.emit("Progress update", progress_percent=50.0)

        calls = mock_publish.call_args_list
        stages = [c[0][0].payload.stage for c in calls if hasattr(c[0][0].payload, "stage")]
        assert "working" in stages

        progress_events = [c for c in calls if c[0][0].payload.type == "tool_progress"]
        assert len(progress_events) == 1
        assert progress_events[0][0][0].payload.message == "Progress update"


class TestIntegration:
    """Integration-style tests for the progress module."""

    @patch("tools._progress.publish_event")
    async def test_typical_tool_usage_pattern(self, mock_publish: MagicMock) -> None:
        """Test a typical tool usage pattern with multiple stages."""
        async with tool_progress_context("browser_navigate", "nav-001") as progress:
            progress.set_stage("connecting", "Connecting to server...")
            await asyncio.sleep(0.01)  # Simulate work
            progress.set_stage("loading", "Loading page content...")
            progress.emit("Fetched header", progress_percent=25.0)
            await asyncio.sleep(0.01)
            progress.emit("Fetched body", progress_percent=50.0)
            progress.set_stage("extracting", "Extracting content...")
            await asyncio.sleep(0.01)
            progress.emit("Done", progress_percent=100.0)

        calls = mock_publish.call_args_list
        events = [c[0][0] for c in calls]

        # Verify the sequence of events
        stages = [e.payload.stage for e in events if hasattr(e.payload, "stage")]
        assert stages[0] == "started"
        assert "connecting" in stages
        assert "loading" in stages
        assert "extracting" in stages
        assert stages[-1] == "completed"

        progress_events = [e for e in events if e.payload.type == "tool_progress"]
        assert len(progress_events) == 3
        percents = [e.payload.progress_percent for e in progress_events]
        assert percents == [25.0, 50.0, 100.0]
