"""Unit tests for conversation persistence models."""

from __future__ import annotations

import pytest

from conversations._models import (
    ClearedItem,
    ClearingRecord,
    ConversationSummary,
    SummaryRecord,
)


@pytest.mark.unit
class TestConversationSummary:
    """Tests for ConversationSummary model."""

    def test_construction(self) -> None:
        """Verify summary construction."""
        summary = ConversationSummary(
            conversation_id="conv-1",
            turn_count=3,
            first_message="hello",
            started_at="2026-01-01T00:00:00",
        )
        assert summary.conversation_id == "conv-1"
        assert summary.turn_count == 3


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


@pytest.mark.unit
class TestClearingRecord:
    """Tests for ClearingRecord model."""

    def test_defaults(self) -> None:
        """Verify default values."""
        record = ClearingRecord(id="clr-001")
        assert record.cleared_items == []
        assert record.total_chars_freed == 0

    def test_with_items(self) -> None:
        """Verify construction with cleared items."""
        record = ClearingRecord(
            id="clr-002",
            results_cleared=2,
            cleared_items=[
                ClearedItem(
                    message_index=3,
                    role="tool",
                    tool_name="read_page",
                    cleared_type="tool_result",
                    original_content="big page",
                    original_chars=8,
                ),
            ],
        )
        assert len(record.cleared_items) == 1
        assert record.cleared_items[0].tool_name == "read_page"
