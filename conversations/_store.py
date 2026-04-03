"""Persistence layer for conversation data.

All conversation data is stored under per-conversation subdirectories::

    {home_dir}/conversations/{conv_id}/
        history.json          # main agent LLM messages
        events.json           # agent events for UI streaming
        sub_agents/
            {NAME}_{hex}.json # sub-agent message histories
        summaries/
            {id}.json         # compaction records
        clearings/
            {id}.json         # tool clearing records
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config import load_config

from ._models import ClearingRecord, ConversationSummary, SummaryRecord

logger = logging.getLogger(__name__)


def _get_conversations_dir() -> Path:
    cfg = load_config()
    return Path(cfg.settings.home_dir) / "conversations"


def _get_conv_dir(conversation_id: str) -> Path:
    return _get_conversations_dir() / conversation_id


# -- Conversation history persistence ------------------------------------------


def save_conversation_history(conversation_id: str, messages: list[dict[str, Any]]) -> None:
    """Save raw ConversationHistory messages for a conversation."""
    conv_dir = _get_conv_dir(conversation_id)
    conv_dir.mkdir(parents=True, exist_ok=True)

    path = conv_dir / "history.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(messages, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_conversation_history(conversation_id: str) -> list[dict[str, Any]] | None:
    """Load raw ConversationHistory messages for a conversation."""
    path = _get_conv_dir(conversation_id) / "history.json"
    if not path.exists():
        return None
    try:
        data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
        return data
    except Exception:
        logger.exception("Failed to load conversation history %s", conversation_id)
        return None


# -- Agent event persistence ---------------------------------------------------


def save_agent_events(conversation_id: str, events: list[dict[str, Any]]) -> None:
    """Append agent events for a conversation."""
    conv_dir = _get_conv_dir(conversation_id)
    conv_dir.mkdir(parents=True, exist_ok=True)

    path = conv_dir / "events.json"
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
    path = _get_conv_dir(conversation_id) / "events.json"
    if not path.exists():
        return []
    try:
        data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
        return data
    except Exception:
        logger.exception("Failed to load agent events %s", conversation_id)
        return []


# -- Sub-agent history persistence ---------------------------------------------


def save_sub_agent_history(
    conversation_id: str,
    agent_name: str,
    short_id: str,
    messages: list[dict[str, Any]],
) -> None:
    """Save a sub-agent's message history."""
    sub_dir = _get_conv_dir(conversation_id) / "sub_agents"
    sub_dir.mkdir(parents=True, exist_ok=True)

    path = sub_dir / f"{agent_name}_{short_id}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(messages, indent=2), encoding="utf-8")
    tmp.replace(path)


# -- Conversation metadata persistence ---------------------------------------


def save_conversation_title(conversation_id: str, title: str) -> None:
    """Save or update the title for a conversation.
    
    Titles are stored in a metadata.json file alongside the conversation history.
    This allows titles to be persisted independently of the message history.
    """
    conv_dir = _get_conv_dir(conversation_id)
    conv_dir.mkdir(parents=True, exist_ok=True)
    
    metadata_path = conv_dir / "metadata.json"
    metadata: dict[str, Any] = {"title": title}
    if metadata_path.exists():
        try:
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata = {**existing, "title": title}
        except Exception:
            pass
    
    tmp = metadata_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    tmp.replace(metadata_path)


def load_conversation_metadata(conversation_id: str) -> dict[str, Any]:
    """Load conversation metadata including title.
    
    Returns an empty dict if no metadata exists for the conversation.
    """
    path = _get_conv_dir(conversation_id) / "metadata.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# -- Conversation listing and deletion -----------------------------------------

def list_conversations() -> list[ConversationSummary]:
    """List all conversations by scanning subdirectories."""
    conv_root = _get_conversations_dir()
    if not conv_root.exists():
        return []

    summaries: list[ConversationSummary] = []
    for entry in conv_root.iterdir():
        if not entry.is_dir():
            continue
        history_path = entry / "history.json"
        if not history_path.exists():
            continue
        try:
            messages: list[dict[str, Any]] = json.loads(
                history_path.read_text(encoding="utf-8"),
            )
            user_msgs = [m for m in messages if m.get("role") == "user"]
            first_msg = user_msgs[0].get("content", "") if user_msgs else ""
            # Truncate for listing display
            if len(first_msg) > 200:
                first_msg = first_msg[:200] + "..."
            started_at = datetime.fromtimestamp(
                history_path.stat().st_mtime, tz=UTC,
            ).isoformat()
            
            # Load title from metadata (if available)
            metadata = load_conversation_metadata(entry.name)
            title = metadata.get("title", "")
            
            summaries.append(ConversationSummary(
                conversation_id=entry.name,
                first_message=first_msg,
                title=title,
                started_at=started_at,
                turn_count=len(user_msgs),
            ))
        except Exception:
            logger.exception("Failed to read conversation %s", entry.name)

    summaries.sort(key=lambda s: s.started_at, reverse=True)
    return summaries


def delete_conversation(conversation_id: str) -> bool:
    """Delete a conversation and all its data."""
    conv_dir = _get_conv_dir(conversation_id)
    if not conv_dir.exists():
        return False
    shutil.rmtree(conv_dir)
    # Remove empty parent directories up to the conversations root.
    conv_root = _get_conversations_dir()
    parent = conv_dir.parent
    while parent != conv_root and parent.is_dir():
        try:
            parent.rmdir()  # only succeeds if empty
            parent = parent.parent
        except OSError:
            break
    return True


# -- Summary record persistence ------------------------------------------------


def save_summary_record(record: SummaryRecord) -> None:
    """Persist a summary record to {conv_id}/summaries/{id}.json."""
    conv_id = record.conversation_id or "default"
    summaries_dir = _get_conv_dir(conv_id) / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)

    path = summaries_dir / f"{record.id}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(record.model_dump(), indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def load_summary_record(conversation_id: str, record_id: str) -> SummaryRecord | None:
    """Load a summary record by conversation and record ID."""
    path = _get_conv_dir(conversation_id) / "summaries" / f"{record_id}.json"
    if not path.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return SummaryRecord.model_validate(data)
    except Exception:
        logger.exception("Failed to load summary record %s", record_id)
        return None


def list_summary_records(conversation_id: str | None = None) -> list[SummaryRecord]:
    """Load summary records, optionally filtered by conversation."""
    dirs_to_scan: list[Path] = []
    if conversation_id:
        summaries_dir = _get_conv_dir(conversation_id) / "summaries"
        if summaries_dir.exists():
            dirs_to_scan.append(summaries_dir)
    else:
        conv_root = _get_conversations_dir()
        if conv_root.exists():
            for entry in conv_root.iterdir():
                if entry.is_dir():
                    sd = entry / "summaries"
                    if sd.exists():
                        dirs_to_scan.append(sd)

    records: list[SummaryRecord] = []
    for d in dirs_to_scan:
        for path in d.glob("*.json"):
            try:
                data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
                records.append(SummaryRecord.model_validate(data))
            except Exception:
                logger.exception("Failed to load summary record from %s", path)

    records.sort(key=lambda r: r.created_at, reverse=True)
    return records


# -- Clearing record persistence -----------------------------------------------


def save_clearing_record(record: ClearingRecord) -> None:
    """Persist a clearing record to {conv_id}/clearings/{id}.json."""
    conv_id = record.conversation_id or "default"
    clearings_dir = _get_conv_dir(conv_id) / "clearings"
    clearings_dir.mkdir(parents=True, exist_ok=True)

    path = clearings_dir / f"{record.id}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(record.model_dump(), indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def load_clearing_record(conversation_id: str, record_id: str) -> ClearingRecord | None:
    """Load a clearing record by conversation and record ID."""
    path = _get_conv_dir(conversation_id) / "clearings" / f"{record_id}.json"
    if not path.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return ClearingRecord.model_validate(data)
    except Exception:
        logger.exception("Failed to load clearing record %s", record_id)
        return None


def list_clearing_records(conversation_id: str | None = None) -> list[ClearingRecord]:
    """Load clearing records, optionally filtered by conversation."""
    dirs_to_scan: list[Path] = []
    if conversation_id:
        clearings_dir = _get_conv_dir(conversation_id) / "clearings"
        if clearings_dir.exists():
            dirs_to_scan.append(clearings_dir)
    else:
        conv_root = _get_conversations_dir()
        if conv_root.exists():
            for entry in conv_root.iterdir():
                if entry.is_dir():
                    cd = entry / "clearings"
                    if cd.exists():
                        dirs_to_scan.append(cd)

    records: list[ClearingRecord] = []
    for d in dirs_to_scan:
        for path in d.glob("*.json"):
            try:
                data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
                records.append(ClearingRecord.model_validate(data))
            except Exception:
                logger.exception("Failed to load clearing record from %s", path)

    records.sort(key=lambda r: r.created_at, reverse=True)
    return records
