"""Unit tests for conversation persistence store."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from conversations._models import (
    ClearingRecord,
    SummaryRecord,
)
from conversations._store import (
    delete_conversation,
    list_clearing_records,
    list_conversations,
    list_summary_records,
    load_clearing_record,
    load_conversation_history,
    load_summary_record,
    save_clearing_record,
    save_conversation_history,
    save_sub_agent_history,
    save_summary_record,
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

        # Verify directory structure
        assert (_conv_dir / "conv-1" / "history.json").exists()

    def test_load_nonexistent(self, _conv_dir: Path) -> None:
        """Loading missing history returns None."""
        assert load_conversation_history("missing") is None


@pytest.mark.unit
class TestSubAgentHistory:
    """Tests for sub-agent history persistence."""

    def test_save_sub_agent(self, _conv_dir: Path) -> None:
        """Save sub-agent history to sub_agents directory."""
        messages = [
            {"role": "user", "content": "browse CNN"},
            {"role": "assistant", "content": "Opening CNN..."},
        ]
        save_sub_agent_history("conv-1", "BROWSER_AGENT", "abc12345", messages)

        path = _conv_dir / "conv-1" / "sub_agents" / "BROWSER_AGENT_abc12345.json"
        assert path.exists()


@pytest.mark.unit
class TestListConversations:
    """Tests for conversation listing."""

    def test_list_conversations(self, _conv_dir: Path) -> None:
        """List conversations from subdirectories."""
        save_conversation_history("conv-1", [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "bye"},
        ])
        save_conversation_history("conv-2", [
            {"role": "user", "content": "search for flights"},
        ])

        summaries = list_conversations()
        assert len(summaries) == 2
        by_id = {s.conversation_id: s for s in summaries}
        assert by_id["conv-1"].turn_count == 2
        assert by_id["conv-1"].first_message == "hello"
        assert by_id["conv-2"].turn_count == 1

    def test_list_empty(self, _conv_dir: Path) -> None:
        """Listing with no conversations returns empty list."""
        assert list_conversations() == []


@pytest.mark.unit
class TestDeleteConversation:
    """Tests for conversation deletion."""

    def test_delete(self, _conv_dir: Path) -> None:
        """Delete removes the entire conversation directory."""
        save_conversation_history("conv-1", [{"role": "user", "content": "hi"}])
        assert delete_conversation("conv-1") is True
        assert not (_conv_dir / "conv-1").exists()

    def test_delete_nonexistent(self, _conv_dir: Path) -> None:
        """Deleting a missing conversation returns False."""
        assert delete_conversation("nope") is False


def _make_summary_record(
    record_id: str = "sum-001",
    conversation_id: str = "conv-1",
    created_at: str = "2026-03-14T12:00:00+00:00",
) -> SummaryRecord:
    return SummaryRecord(
        id=record_id,
        created_at=created_at,
        conversation_id=conversation_id,
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
        loaded = load_summary_record("conv-1", "sum-001")
        assert loaded is not None
        assert loaded.id == "sum-001"
        assert loaded.model == "glm-4.7-flash:q8_0"

        # Verify directory structure
        assert (_conv_dir / "conv-1" / "summaries" / "sum-001.json").exists()

    def test_load_nonexistent(self, _conv_dir: Path) -> None:
        """Loading a missing summary record returns None."""
        assert load_summary_record("conv-1", "missing-id") is None

    def test_list_all(self, _conv_dir: Path) -> None:
        """List summary records across all conversations."""
        save_summary_record(_make_summary_record("s1", "conv-1", "2026-03-14T10:00:00"))
        save_summary_record(_make_summary_record("s2", "conv-2", "2026-03-14T12:00:00"))

        records = list_summary_records()
        assert len(records) == 2
        assert records[0].id == "s2"

    def test_list_by_conversation(self, _conv_dir: Path) -> None:
        """List summary records for a specific conversation."""
        save_summary_record(_make_summary_record("s1", "conv-1"))
        save_summary_record(_make_summary_record("s2", "conv-2"))

        records = list_summary_records(conversation_id="conv-1")
        assert len(records) == 1
        assert records[0].id == "s1"

    def test_list_empty(self, _conv_dir: Path) -> None:
        """Listing with no records returns empty list."""
        assert list_summary_records() == []


@pytest.mark.unit
class TestClearingRecordStore:
    """Tests for clearing record persistence."""

    def test_save_and_load(self, _conv_dir: Path) -> None:
        """Save a clearing record and load it back."""
        record = ClearingRecord(
            id="clr-001",
            conversation_id="conv-1",
            results_cleared=5,
            total_chars_freed=10000,
        )
        save_clearing_record(record)
        loaded = load_clearing_record("conv-1", "clr-001")
        assert loaded is not None
        assert loaded.results_cleared == 5

        # Verify directory structure
        assert (_conv_dir / "conv-1" / "clearings" / "clr-001.json").exists()

    def test_list_all(self, _conv_dir: Path) -> None:
        """List clearing records across all conversations."""
        save_clearing_record(ClearingRecord(
            id="c1", conversation_id="conv-1", created_at="2026-03-14T10:00:00",
        ))
        save_clearing_record(ClearingRecord(
            id="c2", conversation_id="conv-2", created_at="2026-03-14T12:00:00",
        ))

        records = list_clearing_records()
        assert len(records) == 2

    def test_list_by_conversation(self, _conv_dir: Path) -> None:
        """List clearing records for a specific conversation."""
        save_clearing_record(ClearingRecord(id="c1", conversation_id="conv-1"))
        save_clearing_record(ClearingRecord(id="c2", conversation_id="conv-2"))

        records = list_clearing_records(conversation_id="conv-1")
        assert len(records) == 1
        assert records[0].id == "c1"
