"""Unit tests for conversation persistence store."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tools.conversations._models import (
    ConversationMetadata,
    ConversationRecord,
    TurnRecord,
)
from tools.conversations._store import (
    delete_conversation,
    list_conversations,
    load_conversation,
    mark_analyzed,
    save_conversation,
    update_conversation_metadata,
)


@pytest.fixture()
def _conv_dir(tmp_path: Path) -> Path:
    """Patch the conversations directory to a temp directory."""
    conv_dir = tmp_path / "conversations"
    with patch(
        "tools.conversations._store._get_conversations_dir",
        return_value=conv_dir,
    ):
        yield conv_dir


def _make_record(
    record_id: str = "test-001",
    user_message: str = "hello",
    outcome: str = "success",
) -> ConversationRecord:
    return ConversationRecord(
        id=record_id,
        user_message=user_message,
        agent="COMPUTRON_9000",
        started_at="2026-01-01T00:00:00",
        ended_at="2026-01-01T00:01:00",
        turns=[TurnRecord(role="user", content=user_message)],
        metadata=ConversationMetadata(outcome=outcome),
    )


@pytest.mark.unit
class TestConversationStore:
    """Tests for conversation CRUD operations."""

    def test_save_and_load(self, _conv_dir: Path) -> None:
        """Save a conversation and load it back."""
        record = _make_record()
        save_conversation(record)
        loaded = load_conversation("test-001")
        assert loaded is not None
        assert loaded.id == "test-001"
        assert loaded.user_message == "hello"
        assert len(loaded.turns) == 1

    def test_load_nonexistent(self, _conv_dir: Path) -> None:
        """Loading a missing conversation returns None."""
        assert load_conversation("missing-id") is None

    def test_list_conversations(self, _conv_dir: Path) -> None:
        """List conversations with filtering."""
        save_conversation(_make_record("r1", outcome="success"))
        save_conversation(_make_record("r2", outcome="failure"))
        save_conversation(_make_record("r3", outcome="success"))

        all_convs = list_conversations()
        assert len(all_convs) == 3

        successes = list_conversations(outcome="success")
        assert len(successes) == 2

        failures = list_conversations(outcome="failure")
        assert len(failures) == 1

    def test_list_with_pagination(self, _conv_dir: Path) -> None:
        """List conversations with limit and offset."""
        for i in range(5):
            save_conversation(_make_record(f"r{i}", outcome="success"))

        page1 = list_conversations(limit=2, offset=0)
        assert len(page1) == 2

        page2 = list_conversations(limit=2, offset=2)
        assert len(page2) == 2

    def test_delete_conversation(self, _conv_dir: Path) -> None:
        """Delete a conversation removes it from disk and index."""
        save_conversation(_make_record("del-me"))
        assert delete_conversation("del-me") is True
        assert load_conversation("del-me") is None
        assert len(list_conversations()) == 0

    def test_delete_nonexistent(self, _conv_dir: Path) -> None:
        """Deleting a missing conversation returns False."""
        assert delete_conversation("nope") is False

    def test_mark_analyzed(self, _conv_dir: Path) -> None:
        """Mark a conversation as analyzed in both index and record."""
        save_conversation(_make_record("analyze-me"))
        mark_analyzed("analyze-me")

        entries = list_conversations(analyzed=True)
        assert len(entries) == 1
        assert entries[0].id == "analyze-me"

        record = load_conversation("analyze-me")
        assert record is not None
        assert record.metadata.analyzed is True

    def test_update_metadata(self, _conv_dir: Path) -> None:
        """Update specific metadata fields."""
        save_conversation(_make_record("update-me"))
        update_conversation_metadata("update-me", outcome="partial", task_category="web_scraping")

        record = load_conversation("update-me")
        assert record is not None
        assert record.metadata.outcome == "partial"
        assert record.metadata.task_category == "web_scraping"

    def test_update_metadata_nonexistent(self, _conv_dir: Path) -> None:
        """Updating missing conversation returns False."""
        assert update_conversation_metadata("nope", outcome="success") is False

    def test_save_overwrites_existing(self, _conv_dir: Path) -> None:
        """Saving with same ID replaces the record."""
        save_conversation(_make_record("same-id", user_message="first"))
        save_conversation(_make_record("same-id", user_message="second"))

        loaded = load_conversation("same-id")
        assert loaded is not None
        assert loaded.user_message == "second"

        # Index should have exactly one entry
        entries = list_conversations()
        assert len(entries) == 1
