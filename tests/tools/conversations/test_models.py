"""Unit tests for conversation persistence models."""

from __future__ import annotations

import pytest

from tools.conversations._models import (
    ConversationIndexEntry,
    ConversationMetadata,
    ConversationRecord,
    ToolCallRecord,
    TurnRecord,
)


@pytest.mark.unit
class TestToolCallRecord:
    """Tests for ToolCallRecord model."""

    def test_defaults(self) -> None:
        """Verify default values for optional fields."""
        record = ToolCallRecord(name="click")
        assert record.name == "click"
        assert record.arguments == {}
        assert record.result_summary == ""
        assert record.duration_ms is None
        assert record.success is True

    def test_full_construction(self) -> None:
        """Verify all fields can be set."""
        record = ToolCallRecord(
            name="fill_field",
            arguments={"ref": "7", "value": "hello"},
            result_summary="Field filled",
            duration_ms=150,
            success=True,
        )
        assert record.name == "fill_field"
        assert record.arguments["ref"] == "7"
        assert record.duration_ms == 150


@pytest.mark.unit
class TestTurnRecord:
    """Tests for TurnRecord model."""

    def test_assistant_turn(self) -> None:
        """Assistant turn with tool calls."""
        turn = TurnRecord(
            role="assistant",
            content="Let me search for that.",
            tool_calls=[ToolCallRecord(name="open_url")],
            agent_name="BROWSER_AGENT",
            depth=1,
            timestamp="2026-01-01T00:00:00",
        )
        assert turn.role == "assistant"
        assert len(turn.tool_calls) == 1
        assert turn.depth == 1

    def test_tool_turn(self) -> None:
        """Tool result turn."""
        turn = TurnRecord(role="tool", content="Page opened successfully")
        assert turn.role == "tool"
        assert turn.agent_name is None
        assert turn.depth == 0


@pytest.mark.unit
class TestConversationMetadata:
    """Tests for ConversationMetadata model."""

    def test_defaults(self) -> None:
        """Verify sensible defaults."""
        meta = ConversationMetadata()
        assert meta.outcome == "unknown"
        assert meta.total_tool_calls == 0
        assert meta.skill_applied is None
        assert meta.analyzed is False


@pytest.mark.unit
class TestConversationRecord:
    """Tests for ConversationRecord model."""

    def test_minimal(self) -> None:
        """Minimal valid record."""
        record = ConversationRecord(id="test-123")
        assert record.id == "test-123"
        assert record.turns == []
        assert record.metadata.outcome == "unknown"

    def test_serialization_roundtrip(self) -> None:
        """Verify model_dump and model_validate roundtrip."""
        record = ConversationRecord(
            id="test-456",
            user_message="find recipes",
            agent="COMPUTRON_9000",
            turns=[
                TurnRecord(role="user", content="find recipes"),
                TurnRecord(
                    role="assistant",
                    content="Searching...",
                    tool_calls=[ToolCallRecord(name="browser_agent_tool")],
                ),
            ],
            metadata=ConversationMetadata(
                task_summary="Recipe search",
                outcome="success",
                total_tool_calls=3,
            ),
        )
        data = record.model_dump()
        restored = ConversationRecord.model_validate(data)
        assert restored.id == "test-456"
        assert len(restored.turns) == 2
        assert restored.metadata.outcome == "success"


@pytest.mark.unit
class TestConversationIndexEntry:
    """Tests for ConversationIndexEntry model."""

    def test_construction(self) -> None:
        """Verify index entry construction."""
        entry = ConversationIndexEntry(
            id="abc-123",
            user_message="test",
            outcome="success",
        )
        assert entry.id == "abc-123"
        assert entry.analyzed is False
