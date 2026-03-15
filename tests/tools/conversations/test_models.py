"""Unit tests for conversation persistence models."""

from __future__ import annotations

import pytest

from conversations._models import (
    ConversationSummary,
    MessageRecord,
    SummaryRecord,
    ToolCallRecord,
    TurnIndexEntry,
    TurnMetadata,
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
class TestMessageRecord:
    """Tests for MessageRecord model."""

    def test_assistant_message(self) -> None:
        """Assistant message with tool calls."""
        msg = MessageRecord(
            role="assistant",
            content="Let me search for that.",
            tool_calls=[ToolCallRecord(name="open_url")],
            agent_name="BROWSER_AGENT",
            depth=1,
            timestamp="2026-01-01T00:00:00",
        )
        assert msg.role == "assistant"
        assert len(msg.tool_calls) == 1
        assert msg.depth == 1

    def test_tool_message(self) -> None:
        """Tool result message."""
        msg = MessageRecord(role="tool", content="Page opened successfully")
        assert msg.role == "tool"
        assert msg.agent_name is None
        assert msg.depth == 0


@pytest.mark.unit
class TestTurnMetadata:
    """Tests for TurnMetadata model."""

    def test_defaults(self) -> None:
        """Verify sensible defaults."""
        meta = TurnMetadata()
        assert meta.outcome == "unknown"
        assert meta.total_tool_calls == 0
        assert meta.skill_applied is None
        assert meta.analyzed is False


@pytest.mark.unit
class TestTurnRecord:
    """Tests for TurnRecord model."""

    def test_minimal(self) -> None:
        """Minimal valid record."""
        record = TurnRecord(id="test-123")
        assert record.id == "test-123"
        assert record.messages == []
        assert record.metadata.outcome == "unknown"

    def test_serialization_roundtrip(self) -> None:
        """Verify model_dump and model_validate roundtrip."""
        record = TurnRecord(
            id="test-456",
            user_message="find recipes",
            agent="COMPUTRON_9000",
            messages=[
                MessageRecord(role="user", content="find recipes"),
                MessageRecord(
                    role="assistant",
                    content="Searching...",
                    tool_calls=[ToolCallRecord(name="browser_agent_tool")],
                ),
            ],
            metadata=TurnMetadata(
                task_summary="Recipe search",
                outcome="success",
                total_tool_calls=3,
            ),
        )
        data = record.model_dump()
        restored = TurnRecord.model_validate(data)
        assert restored.id == "test-456"
        assert len(restored.messages) == 2
        assert restored.metadata.outcome == "success"


@pytest.mark.unit
class TestTurnIndexEntry:
    """Tests for TurnIndexEntry model."""

    def test_construction(self) -> None:
        """Verify index entry construction."""
        entry = TurnIndexEntry(
            id="abc-123",
            conversation_id="conv-1",
            user_message="test",
            outcome="success",
        )
        assert entry.id == "abc-123"
        assert entry.conversation_id == "conv-1"
        assert entry.analyzed is False


@pytest.mark.unit
class TestConversationSummary:
    """Tests for ConversationSummary model."""

    def test_construction(self) -> None:
        """Verify summary construction."""
        summary = ConversationSummary(
            conversation_id="conv-1",
            turn_count=3,
            first_message="hello",
            outcomes=["success", "success", "partial"],
            started_at="2026-01-01T00:00:00",
            ended_at="2026-01-01T00:05:00",
        )
        assert summary.conversation_id == "conv-1"
        assert summary.turn_count == 3
        assert len(summary.outcomes) == 3
        assert summary.analyzed is False


@pytest.mark.unit
class TestSummaryRecord:
    """Tests for SummaryRecord model."""

    def test_defaults(self) -> None:
        """Verify default values for optional fields."""
        record = SummaryRecord(id="sum-001")
        assert record.id == "sum-001"
        assert record.input_messages == []
        assert record.input_char_count == 0
        assert record.prior_summary is None
        assert record.summary_text == ""
        assert record.fill_ratio == 0.0

    def test_serialization_roundtrip(self) -> None:
        """Verify model_dump and model_validate roundtrip."""
        record = SummaryRecord(
            id="sum-002",
            created_at="2026-03-14T12:00:00+00:00",
            model="glm-4.7-flash:q8_0",
            input_messages=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ],
            input_char_count=500,
            prior_summary="Previous context summary.",
            summary_text="User greeted the assistant.",
            summary_char_count=27,
            messages_compacted=2,
            fill_ratio=0.82,
        )
        data = record.model_dump()
        restored = SummaryRecord.model_validate(data)
        assert restored.id == "sum-002"
        assert restored.model == "glm-4.7-flash:q8_0"
        assert len(restored.input_messages) == 2
        assert restored.prior_summary == "Previous context summary."
        assert restored.fill_ratio == 0.82
