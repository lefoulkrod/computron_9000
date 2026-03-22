"""Persistence layer for turn records and conversation history."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from config import load_config

from ._models import ConversationSummary, SummaryRecord, TurnIndexEntry, TurnRecord

logger = logging.getLogger(__name__)


def _get_conversations_dir() -> Path:
    cfg = load_config()
    return Path(cfg.settings.home_dir) / "conversations"


def _get_summaries_dir() -> Path:
    return _get_conversations_dir() / "summaries"


def _get_index_path() -> Path:
    return _get_conversations_dir() / "index.json"


def _load_index() -> list[TurnIndexEntry]:
    """Read the turn index. Returns empty list if missing."""
    path = _get_index_path()
    if not path.exists():
        return []
    try:
        data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
        return [TurnIndexEntry.model_validate(entry) for entry in data]
    except Exception:
        logger.exception("Failed to load turn index from %s", path)
        return []


def _save_index(entries: list[TurnIndexEntry]) -> None:
    """Atomically write the turn index."""
    path = _get_index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    serialized = [e.model_dump() for e in entries]
    tmp.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
    tmp.replace(path)


def save_turn(record: TurnRecord) -> None:
    """Persist a turn record and update the index."""
    conv_dir = _get_conversations_dir()
    conv_dir.mkdir(parents=True, exist_ok=True)

    # Write the full turn file
    turn_path = conv_dir / f"{record.id}.json"
    tmp = turn_path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(record.model_dump(), indent=2),
        encoding="utf-8",
    )
    tmp.replace(turn_path)

    # Update the index
    index = _load_index()
    entry = TurnIndexEntry(
        id=record.id,
        conversation_id=record.conversation_id,
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


def load_turn(turn_id: str) -> TurnRecord | None:
    """Load a full turn by ID."""
    path = _get_conversations_dir() / f"{turn_id}.json"
    if not path.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return TurnRecord.model_validate(data)
    except Exception:
        logger.exception("Failed to load turn %s", turn_id)
        return None


def list_turns(
    *,
    limit: int = 50,
    offset: int = 0,
    outcome: str | None = None,
    analyzed: bool | None = None,
) -> list[TurnIndexEntry]:
    """List turn index entries with optional filtering."""
    entries = _load_index()

    if outcome is not None:
        entries = [e for e in entries if e.outcome == outcome]
    if analyzed is not None:
        entries = [e for e in entries if e.analyzed == analyzed]

    # Sort by started_at descending (most recent first)
    entries.sort(key=lambda e: e.started_at, reverse=True)
    return entries[offset : offset + limit]


def mark_analyzed(turn_id: str) -> None:
    """Mark a turn as analyzed in the index."""
    index = _load_index()
    for entry in index:
        if entry.id == turn_id:
            entry.analyzed = True
            break
    _save_index(index)

    # Also update the full record
    record = load_turn(turn_id)
    if record:
        record.metadata.analyzed = True
        save_turn(record)


def delete_turn(turn_id: str) -> bool:
    """Delete a turn by ID. Returns True if found."""
    turn_path = _get_conversations_dir() / f"{turn_id}.json"
    if not turn_path.exists():
        return False

    turn_path.unlink()

    # Remove from index
    index = _load_index()
    index = [e for e in index if e.id != turn_id]
    _save_index(index)
    return True


def update_turn_metadata(
    turn_id: str,
    **kwargs: Any,
) -> bool:
    """Update specific metadata fields on a turn record."""
    record = load_turn(turn_id)
    if record is None:
        return False

    for key, value in kwargs.items():
        if hasattr(record.metadata, key):
            setattr(record.metadata, key, value)

    save_turn(record)
    return True


def delete_conversation(conversation_id: str) -> bool:
    """Delete all turns and history for a conversation. Returns True if anything was deleted."""
    conv_dir = _get_conversations_dir()
    index = _load_index()
    turn_ids = [e.id for e in index if e.conversation_id == conversation_id]

    if not turn_ids:
        # Still try to delete the history file
        history_path = conv_dir / f"{conversation_id}_history.json"
        if history_path.exists():
            history_path.unlink()
            return True
        return False

    # Delete turn files
    for tid in turn_ids:
        turn_path = conv_dir / f"{tid}.json"
        if turn_path.exists():
            turn_path.unlink()

    # Remove from index
    remaining = [e for e in index if e.conversation_id != conversation_id]
    _save_index(remaining)

    # Delete history and sub-agent files
    for suffix in ("_history.json", "_sub_agents.json", "_agent_events.json"):
        path = conv_dir / f"{conversation_id}{suffix}"
        if path.exists():
            path.unlink()

    return True


# -- Conversation history persistence (full-fidelity LLM messages) ----------


def save_conversation_history(conversation_id: str, messages: list[dict[str, Any]]) -> None:
    """Save raw ConversationHistory messages for a conversation."""
    conv_dir = _get_conversations_dir()
    conv_dir.mkdir(parents=True, exist_ok=True)

    path = conv_dir / f"{conversation_id}_history.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(messages, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_conversation_history(conversation_id: str) -> list[dict[str, Any]] | None:
    """Load raw ConversationHistory messages for a conversation."""
    path = _get_conversations_dir() / f"{conversation_id}_history.json"
    if not path.exists():
        return None
    try:
        data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
        return data
    except Exception:
        logger.exception("Failed to load conversation history %s", conversation_id)
        return None


def save_sub_agent_histories(conversation_id: str, histories: list[dict[str, Any]]) -> None:
    """Append sub-agent histories for a conversation.

    Each entry is {"agent_name": str, "parent_tool": str, "messages": list[dict]}.
    Accumulates across turns — each call appends to the existing file.
    """
    conv_dir = _get_conversations_dir()
    conv_dir.mkdir(parents=True, exist_ok=True)

    path = conv_dir / f"{conversation_id}_sub_agents.json"
    existing: list[dict[str, Any]] = []
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to load sub-agent histories %s", conversation_id)

    existing.extend(histories)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_sub_agent_histories(conversation_id: str) -> list[dict[str, Any]]:
    """Load sub-agent histories for a conversation."""
    path = _get_conversations_dir() / f"{conversation_id}_sub_agents.json"
    if not path.exists():
        return []
    try:
        data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
        return data
    except Exception:
        logger.exception("Failed to load sub-agent histories %s", conversation_id)
        return []


# -- Agent event persistence ------------------------------------------------


def save_agent_events(conversation_id: str, events: list[dict[str, Any]]) -> None:
    """Append agent events for a conversation.

    Accumulates across turns — each call appends to the existing file.
    """
    conv_dir = _get_conversations_dir()
    conv_dir.mkdir(parents=True, exist_ok=True)

    path = conv_dir / f"{conversation_id}_agent_events.json"
    existing: list[dict[str, Any]] = []
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to load agent events %s", conversation_id)

    existing.extend(events)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_agent_events(conversation_id: str) -> list[dict[str, Any]]:
    """Load agent events for a conversation."""
    path = _get_conversations_dir() / f"{conversation_id}_agent_events.json"
    if not path.exists():
        return []
    try:
        data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
        return data
    except Exception:
        logger.exception("Failed to load agent events %s", conversation_id)
        return []


# -- Conversation-level queries --------------------------------------------


def list_conversations(
    *,
    analyzed: bool | None = None,
) -> list[ConversationSummary]:
    """Group turns by conversation_id and return conversation summaries."""
    entries = _load_index()

    # Group by conversation_id
    groups: dict[str, list[TurnIndexEntry]] = {}
    for e in entries:
        groups.setdefault(e.conversation_id, []).append(e)

    summaries: list[ConversationSummary] = []
    for conv_id, turns in groups.items():
        turns.sort(key=lambda t: t.started_at)
        all_analyzed = all(t.analyzed for t in turns)

        if analyzed is not None and all_analyzed != analyzed:
            continue

        total_tool_calls = 0
        outcomes: list[str] = []
        for t in turns:
            outcomes.append(t.outcome)
            # Tool call count loaded from full record would be expensive;
            # we approximate from index data (0 per entry).

        summaries.append(ConversationSummary(
            conversation_id=conv_id,
            turn_count=len(turns),
            first_message=turns[0].user_message if turns else "",
            outcomes=outcomes,
            started_at=turns[0].started_at if turns else "",
            ended_at=turns[-1].started_at if turns else "",
            total_tool_calls=total_tool_calls,
            analyzed=all_analyzed,
        ))

    # Sort by started_at descending
    summaries.sort(key=lambda s: s.started_at, reverse=True)
    return summaries


def load_conversation_turns(conversation_id: str) -> list[TurnRecord]:
    """Load all turns for a conversation, sorted by started_at."""
    entries = _load_index()
    turn_ids = [e.id for e in entries if e.conversation_id == conversation_id]

    turns: list[TurnRecord] = []
    for tid in turn_ids:
        record = load_turn(tid)
        if record:
            turns.append(record)

    turns.sort(key=lambda t: t.started_at)
    return turns


def mark_conversation_analyzed(conversation_id: str) -> None:
    """Mark all turns in a conversation as analyzed."""
    index = _load_index()
    changed = False
    for entry in index:
        if entry.conversation_id == conversation_id and not entry.analyzed:
            entry.analyzed = True
            changed = True
    if changed:
        _save_index(index)

    # Also update full records
    for entry in index:
        if entry.conversation_id == conversation_id:
            record = load_turn(entry.id)
            if record and not record.metadata.analyzed:
                record.metadata.analyzed = True
                save_turn(record)


# -- Summary record persistence ------------------------------------------------


def save_summary_record(record: SummaryRecord) -> None:
    """Persist a summary record to conversations/summaries/{id}.json."""
    summaries_dir = _get_summaries_dir()
    summaries_dir.mkdir(parents=True, exist_ok=True)

    path = summaries_dir / f"{record.id}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(record.model_dump(), indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def load_summary_record(record_id: str) -> SummaryRecord | None:
    """Load a summary record by ID."""
    path = _get_summaries_dir() / f"{record_id}.json"
    if not path.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return SummaryRecord.model_validate(data)
    except Exception:
        logger.exception("Failed to load summary record %s", record_id)
        return None


def list_summary_records() -> list[SummaryRecord]:
    """Load all summary records, sorted by created_at descending."""
    summaries_dir = _get_summaries_dir()
    if not summaries_dir.exists():
        return []

    records: list[SummaryRecord] = []
    for path in summaries_dir.glob("*.json"):
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            records.append(SummaryRecord.model_validate(data))
        except Exception:
            logger.exception("Failed to load summary record from %s", path)

    records.sort(key=lambda r: r.created_at, reverse=True)
    return records
