"""Persistence layer for conversation records."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from config import load_config

from ._models import ConversationIndexEntry, ConversationRecord

logger = logging.getLogger(__name__)


def _get_conversations_dir() -> Path:
    cfg = load_config()
    return Path(cfg.settings.home_dir) / "conversations"


def _get_index_path() -> Path:
    return _get_conversations_dir() / "index.json"


def _load_index() -> list[ConversationIndexEntry]:
    """Read the conversation index. Returns empty list if missing."""
    path = _get_index_path()
    if not path.exists():
        return []
    try:
        data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
        return [ConversationIndexEntry.model_validate(entry) for entry in data]
    except Exception:
        logger.exception("Failed to load conversation index from %s", path)
        return []


def _save_index(entries: list[ConversationIndexEntry]) -> None:
    """Atomically write the conversation index."""
    path = _get_index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    serialized = [e.model_dump() for e in entries]
    tmp.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
    tmp.replace(path)


def save_conversation(record: ConversationRecord) -> None:
    """Persist a conversation record and update the index."""
    conv_dir = _get_conversations_dir()
    conv_dir.mkdir(parents=True, exist_ok=True)

    # Write the full conversation file
    conv_path = conv_dir / f"{record.id}.json"
    tmp = conv_path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(record.model_dump(), indent=2),
        encoding="utf-8",
    )
    tmp.replace(conv_path)

    # Update the index
    index = _load_index()
    entry = ConversationIndexEntry(
        id=record.id,
        user_message=record.user_message,
        task_category=record.metadata.task_category,
        outcome=record.metadata.outcome,
        started_at=record.started_at,
        skill_applied=record.metadata.skill_applied,
        analyzed=record.metadata.analyzed,
    )
    # Replace existing entry or append
    existing_idx = next((i for i, e in enumerate(index) if e.id == record.id), None)
    if existing_idx is not None:
        index[existing_idx] = entry
    else:
        index.append(entry)
    _save_index(index)


def load_conversation(conversation_id: str) -> ConversationRecord | None:
    """Load a full conversation by ID."""
    path = _get_conversations_dir() / f"{conversation_id}.json"
    if not path.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return ConversationRecord.model_validate(data)
    except Exception:
        logger.exception("Failed to load conversation %s", conversation_id)
        return None


def list_conversations(
    *,
    limit: int = 50,
    offset: int = 0,
    outcome: str | None = None,
    analyzed: bool | None = None,
) -> list[ConversationIndexEntry]:
    """List conversation index entries with optional filtering."""
    entries = _load_index()

    if outcome is not None:
        entries = [e for e in entries if e.outcome == outcome]
    if analyzed is not None:
        entries = [e for e in entries if e.analyzed == analyzed]

    # Sort by started_at descending (most recent first)
    entries.sort(key=lambda e: e.started_at, reverse=True)
    return entries[offset : offset + limit]


def mark_analyzed(conversation_id: str) -> None:
    """Mark a conversation as analyzed in the index."""
    index = _load_index()
    for entry in index:
        if entry.id == conversation_id:
            entry.analyzed = True
            break
    _save_index(index)

    # Also update the full record
    record = load_conversation(conversation_id)
    if record:
        record.metadata.analyzed = True
        save_conversation(record)


def delete_conversation(conversation_id: str) -> bool:
    """Delete a conversation by ID. Returns True if found."""
    conv_path = _get_conversations_dir() / f"{conversation_id}.json"
    if not conv_path.exists():
        return False

    conv_path.unlink()

    # Remove from index
    index = _load_index()
    index = [e for e in index if e.id != conversation_id]
    _save_index(index)
    return True


def update_conversation_metadata(
    conversation_id: str,
    **kwargs: Any,
) -> bool:
    """Update specific metadata fields on a conversation record."""
    record = load_conversation(conversation_id)
    if record is None:
        return False

    for key, value in kwargs.items():
        if hasattr(record.metadata, key):
            setattr(record.metadata, key, value)

    save_conversation(record)
    return True
