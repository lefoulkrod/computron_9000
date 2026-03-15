"""Unit tests for conversation persistence store."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from conversations._models import (
    MessageRecord,
    SummaryRecord,
    TurnMetadata,
    TurnRecord,
)
from conversations._store import (
    delete_turn,
    list_conversations,
    list_summary_records,
    list_turns,
    load_conversation_history,
    load_conversation_turns,
    load_summary_record,
    load_turn,
    mark_analyzed,
    mark_conversation_analyzed,
    save_conversation_history,
    save_summary_record,
    save_turn,
    update_turn_metadata,
)


@pytest.fixture()
def _conv_dir(tmp_path: Path) -> Path:
    """Patch the conversations directory to a temp directory."""
    conv_dir = tmp_path / "conversations"
    with patch(
        "conversations._store._get_conversations_dir",
        return_value=conv_dir,
    ):
        yield conv_dir


def _make_record(
    record_id: str = "test-001",
    conversation_id: str = "conv-default",
    user_message: str = "hello",
    outcome: str = "success",
) -> TurnRecord:
    return TurnRecord(
        id=record_id,
        conversation_id=conversation_id,
        user_message=user_message,
        agent="COMPUTRON_9000",
        started_at="2026-01-01T00:00:00",
        ended_at="2026-01-01T00:01:00",
        messages=[MessageRecord(role="user", content=user_message)],
        metadata=TurnMetadata(outcome=outcome),
    )


@pytest.mark.unit
class TestTurnStore:
    """Tests for turn CRUD operations."""

    def test_save_and_load(self, _conv_dir: Path) -> None:
        """Save a turn and load it back."""
        record = _make_record()
        save_turn(record)
        loaded = load_turn("test-001")
        assert loaded is not None
        assert loaded.id == "test-001"
        assert loaded.user_message == "hello"
        assert len(loaded.messages) == 1

    def test_load_nonexistent(self, _conv_dir: Path) -> None:
        """Loading a missing turn returns None."""
        assert load_turn("missing-id") is None

    def test_list_turns(self, _conv_dir: Path) -> None:
        """List turns with filtering."""
        save_turn(_make_record("r1", outcome="success"))
        save_turn(_make_record("r2", outcome="failure"))
        save_turn(_make_record("r3", outcome="success"))

        all_turns = list_turns()
        assert len(all_turns) == 3

        successes = list_turns(outcome="success")
        assert len(successes) == 2

        failures = list_turns(outcome="failure")
        assert len(failures) == 1

    def test_list_with_pagination(self, _conv_dir: Path) -> None:
        """List turns with limit and offset."""
        for i in range(5):
            save_turn(_make_record(f"r{i}", outcome="success"))

        page1 = list_turns(limit=2, offset=0)
        assert len(page1) == 2

        page2 = list_turns(limit=2, offset=2)
        assert len(page2) == 2

    def test_delete_turn(self, _conv_dir: Path) -> None:
        """Delete a turn removes it from disk and index."""
        save_turn(_make_record("del-me"))
        assert delete_turn("del-me") is True
        assert load_turn("del-me") is None
        assert len(list_turns()) == 0

    def test_delete_nonexistent(self, _conv_dir: Path) -> None:
        """Deleting a missing turn returns False."""
        assert delete_turn("nope") is False

    def test_mark_analyzed(self, _conv_dir: Path) -> None:
        """Mark a turn as analyzed in both index and record."""
        save_turn(_make_record("analyze-me"))
        mark_analyzed("analyze-me")

        entries = list_turns(analyzed=True)
        assert len(entries) == 1
        assert entries[0].id == "analyze-me"

        record = load_turn("analyze-me")
        assert record is not None
        assert record.metadata.analyzed is True

    def test_update_metadata(self, _conv_dir: Path) -> None:
        """Update specific metadata fields."""
        save_turn(_make_record("update-me"))
        update_turn_metadata("update-me", outcome="partial", task_category="web_scraping")

        record = load_turn("update-me")
        assert record is not None
        assert record.metadata.outcome == "partial"
        assert record.metadata.task_category == "web_scraping"

    def test_update_metadata_nonexistent(self, _conv_dir: Path) -> None:
        """Updating missing turn returns False."""
        assert update_turn_metadata("nope", outcome="success") is False

    def test_save_overwrites_existing(self, _conv_dir: Path) -> None:
        """Saving with same ID replaces the record."""
        save_turn(_make_record("same-id", user_message="first"))
        save_turn(_make_record("same-id", user_message="second"))

        loaded = load_turn("same-id")
        assert loaded is not None
        assert loaded.user_message == "second"

        # Index should have exactly one entry
        entries = list_turns()
        assert len(entries) == 1


@pytest.mark.unit
class TestConversationHistory:
    """Tests for full-fidelity conversation history persistence."""

    def test_save_and_load(self, _conv_dir: Path) -> None:
        """Save and load raw conversation history."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        save_conversation_history("conv-1", messages)
        loaded = load_conversation_history("conv-1")
        assert loaded is not None
        assert len(loaded) == 3
        assert loaded[1]["content"] == "hello"

    def test_load_nonexistent(self, _conv_dir: Path) -> None:
        """Loading missing history returns None."""
        assert load_conversation_history("missing") is None


@pytest.mark.unit
class TestConversationQueries:
    """Tests for conversation-level queries."""

    def test_list_conversations(self, _conv_dir: Path) -> None:
        """Group turns by conversation_id."""
        save_turn(_make_record("t1", conversation_id="conv-1"))
        save_turn(_make_record("t2", conversation_id="conv-1"))
        save_turn(_make_record("t3", conversation_id="conv-2"))

        summaries = list_conversations()
        assert len(summaries) == 2
        conv1 = next(s for s in summaries if s.conversation_id == "conv-1")
        assert conv1.turn_count == 2

    def test_load_conversation_turns(self, _conv_dir: Path) -> None:
        """Load all turns for a conversation."""
        save_turn(_make_record("t1", conversation_id="conv-1"))
        save_turn(_make_record("t2", conversation_id="conv-1"))

        turns = load_conversation_turns("conv-1")
        assert len(turns) == 2

    def test_mark_conversation_analyzed(self, _conv_dir: Path) -> None:
        """Mark all turns in a conversation as analyzed."""
        save_turn(_make_record("t1", conversation_id="conv-1"))
        save_turn(_make_record("t2", conversation_id="conv-1"))
        save_turn(_make_record("t3", conversation_id="conv-2"))

        mark_conversation_analyzed("conv-1")

        # conv-1 turns should be analyzed
        t1 = load_turn("t1")
        t2 = load_turn("t2")
        t3 = load_turn("t3")
        assert t1 is not None and t1.metadata.analyzed is True
        assert t2 is not None and t2.metadata.analyzed is True
        assert t3 is not None and t3.metadata.analyzed is False

    def test_list_conversations_filter_analyzed(self, _conv_dir: Path) -> None:
        """Filter conversations by analyzed status."""
        save_turn(_make_record("t1", conversation_id="conv-1"))
        save_turn(_make_record("t2", conversation_id="conv-2"))
        mark_conversation_analyzed("conv-1")

        unanalyzed = list_conversations(analyzed=False)
        assert len(unanalyzed) == 1
        assert unanalyzed[0].conversation_id == "conv-2"

        analyzed = list_conversations(analyzed=True)
        assert len(analyzed) == 1
        assert analyzed[0].conversation_id == "conv-1"


def _make_summary_record(
    record_id: str = "sum-001",
    created_at: str = "2026-03-14T12:00:00+00:00",
) -> SummaryRecord:
    return SummaryRecord(
        id=record_id,
        created_at=created_at,
        model="glm-4.7-flash:q8_0",
        input_messages=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ],
        input_char_count=200,
        summary_text="User greeted the assistant.",
        summary_char_count=27,
        messages_compacted=2,
        fill_ratio=0.82,
    )


@pytest.mark.unit
class TestSummaryRecordStore:
    """Tests for summary record persistence."""

    def test_save_and_load(self, _conv_dir: Path) -> None:
        """Save a summary record and load it back."""
        record = _make_summary_record()
        save_summary_record(record)
        loaded = load_summary_record("sum-001")
        assert loaded is not None
        assert loaded.id == "sum-001"
        assert loaded.model == "glm-4.7-flash:q8_0"
        assert len(loaded.input_messages) == 2
        assert loaded.summary_text == "User greeted the assistant."

    def test_load_nonexistent(self, _conv_dir: Path) -> None:
        """Loading a missing summary record returns None."""
        assert load_summary_record("missing-id") is None

    def test_list_summary_records(self, _conv_dir: Path) -> None:
        """List summary records sorted by created_at descending."""
        save_summary_record(_make_summary_record("s1", "2026-03-14T10:00:00+00:00"))
        save_summary_record(_make_summary_record("s2", "2026-03-14T12:00:00+00:00"))
        save_summary_record(_make_summary_record("s3", "2026-03-14T11:00:00+00:00"))

        records = list_summary_records()
        assert len(records) == 3
        assert records[0].id == "s2"
        assert records[1].id == "s3"
        assert records[2].id == "s1"

    def test_list_empty(self, _conv_dir: Path) -> None:
        """Listing with no records returns empty list."""
        assert list_summary_records() == []
