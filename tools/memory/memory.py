"""Persistent key-value memory tools for COMPUTRON with semantic search."""

from __future__ import annotations

import json
import logging
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import load_config

logger = logging.getLogger(__name__)


class MemoryCategory:
    """Categories for organizing memories."""

    USER_PREFERENCE = "user_preference"
    TECHNICAL_FACT = "technical_fact"
    PROJECT_CONTEXT = "project_context"
    CONVERSATION_SUMMARY = "conversation_summary"
    GOAL = "goal"
    HABIT = "habit"
    PERSONAL_INFO = "personal_info"
    GENERAL = "general"


@dataclass
class MemoryEntry:
    """A single memory entry with metadata."""

    value: str
    hidden: bool = False
    category: str = MemoryCategory.USER_PREFERENCE
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "value": self.value,
            "hidden": self.hidden,
            "category": self.category,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "access_count": self.access_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
        """Deserialize from dictionary."""
        return cls(
            value=str(data.get("value", "")),
            hidden=bool(data.get("hidden", False)),
            category=str(data.get("category", MemoryCategory.USER_PREFERENCE)),
            tags=list(data.get("tags", [])),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.now(timezone.utc),
            access_count=int(data.get("access_count", 0)),
        )


def _memory_path() -> Path:
    return Path(load_config().settings.home_dir) / "memory.json"


def _profile_path() -> Path:
    return Path(load_config().settings.home_dir) / "user_profile.json"


def _load_raw() -> dict[str, MemoryEntry]:
    """Load all memories from disk."""
    path = _memory_path()
    if not path.exists():
        return {}
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return {k: MemoryEntry.from_dict(v) if isinstance(v, dict) else MemoryEntry(value=str(v), hidden=False) for k, v in data.items()}
    except Exception:
        logger.exception("Failed to load memory from %s", path)
        return {}


def _save_raw(data: dict[str, MemoryEntry]) -> None:
    """Save all memories to disk atomically."""
    path = _memory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = {k: e.to_dict() for k, e in data.items()}
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, suffix=".tmp", encoding="utf-8") as f:
        json.dump(serialized, f, indent=2, ensure_ascii=False)
        tmp = Path(f.name)
    tmp.replace(path)


def _tokenize(text: str) -> set[str]:
    """Simple tokenization for semantic search."""
    text = re.sub(r"[^\w\s]", " ", text.lower())
    tokens = set()
    for word in text.split():
        tokens.update(word.split("_"))
    return set(t for t in tokens if len(t) > 2)


def _calculate_relevance(query: str, key: str, entry: MemoryEntry) -> float:
    """Calculate relevance score for a memory entry."""
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0

    key_tokens = _tokenize(key)
    value_tokens = _tokenize(entry.value)
    category_tokens = _tokenize(entry.category.replace("_", " "))
    tag_tokens = set()
    for tag in entry.tags:
        tag_tokens.update(_tokenize(tag))

    scores = []
    for token in query_tokens:
        score = 0.0
        if token in key_tokens:
            score += 3.0
        if token in value_tokens:
            score += 2.0
        if token in category_tokens:
            score += 1.5
        if token in tag_tokens:
            score += 2.5
        scores.append(score)

    avg_score = sum(scores) / len(query_tokens)
    access_boost = min(entry.access_count / 10.0, 1.0) * 0.5

    return avg_score + access_boost


def _load_profile() -> dict[str, Any]:
    """Load user profile from disk."""
    path = _profile_path()
    if not path.exists():
        return {"preferences": {}, "profile": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to load profile from %s", path)
        return {"preferences": {}, "profile": {}}


def _save_profile(profile: dict[str, Any]) -> None:
    """Save user profile to disk."""
    path = _profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, suffix=".tmp", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
        tmp = Path(f.name)
    tmp.replace(path)


def load_memory() -> dict[str, MemoryEntry]:
    """Load all stored memories."""
    return _load_raw()


def set_key_hidden(key: str, hidden: bool) -> None:
    """Mark a memory key as hidden or visible in the UI."""
    data = _load_raw()
    if key in data:
        data[key].hidden = hidden
        _save_raw(data)


async def remember(
    key: str,
    value: str,
    *,
    category: str = MemoryCategory.USER_PREFERENCE,
    tags: list[str] | None = None,
) -> dict[str, object]:
    """Store a persistent memory that will be available in all future sessions.

    Use this to remember facts about the user, their preferences, useful context,
    or anything worth recalling later. Memories persist indefinitely.

    Args:
        key: Short identifier for the memory (e.g. "user_timezone", "preferred_language").
        value: The value to remember.
        category: Category for organizing memories.
        tags: Optional list of tags for searching.

    Returns:
        Confirmation dict with status and stored key/value.
    """
    data = _load_raw()
    existing_hidden = data[key].hidden if key in data else False
    existing_count = data[key].access_count if key in data else 0
    created_at = data[key].created_at if key in data else datetime.now(timezone.utc)

    data[key] = MemoryEntry(
        value=value,
        hidden=existing_hidden,
        category=category,
        tags=tags or [],
        created_at=created_at,
        updated_at=datetime.now(timezone.utc),
        access_count=existing_count,
    )
    _save_raw(data)
    logger.info("Memory stored: %s = %r (category=%s, tags=%s)", key, value, category, tags)
    return {"status": "ok", "key": key, "value": value, "category": category, "tags": tags or []}


async def forget(key: str) -> dict[str, object]:
    """Remove a stored memory by key.

    Args:
        key: The memory key to delete.

    Returns:
        Confirmation dict with status.
    """
    data = _load_raw()
    if key not in data:
        return {"status": "not_found", "key": key}
    del data[key]
    _save_raw(data)
    logger.info("Memory forgotten: %s", key)
    return {"status": "ok", "key": key}


async def search_memory(
    query: str, *,
    category: str | None = None,
    limit: int = 5,
    min_relevance: float = 0.5
) -> dict[str, object]:
    """Search memories using semantic relevance scoring.

    Finds memories most relevant to the given query based on token matching
    across keys, values, categories, and tags.

    Args:
        query: The search query text.
        category: Optional filter by memory category.
        limit: Maximum number of results to return.
        min_relevance: Minimum relevance score (0-10) to include.

    Returns:
        Dict with status and list of matching memories with relevance scores.
    """
    data = _load_raw()
    results = []

    for key, entry in data.items():
        if entry.hidden:
            continue

        if category is not None and entry.category != category:
            continue

        relevance = _calculate_relevance(query, key, entry)
        if relevance >= min_relevance:
            entry.access_count += 1
            results.append({
                "key": key,
                "value": entry.value,
                "relevance_score": round(relevance, 2),
                "category": entry.category,
                "tags": entry.tags
            })

    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    results = results[:limit]

    _save_raw(data)  # Save updated access counts

    logger.info("Memory search for %r found %d results", query, len(results))
    return {"status": "ok", "results": results, "total_found": len(results)}


async def get_relevant_memories(context: str, *, limit: int = 5) -> dict[str, object]:
    """Get memories relevant to the given context.

    A convenience wrapper around search_memory optimized for retrieving
    memories that might help with the current conversation context.

    Args:
        context: Current conversation context or user message.
        limit: Maximum number of memories to return.

    Returns:
        Dict with status and list of relevant memories organized by category.
    """
    result = await search_memory(context, limit=limit)

    # Organize by category
    by_category: dict[str, list[dict]] = {}
    for mem in result["results"]:
        cat = mem["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(mem)

    return {
        "status": "ok",
        "memories": result["results"],
        "by_category": by_category
    }


async def get_user_profile() -> dict[str, object]:
    """Retrieve the structured user profile.

    Returns the user profile stored in user_profile.json, or an empty
    profile if none exists yet.

    Returns:
        Dict with status and profile data including preferences.
    """
    profile = _load_profile()
    prefs = profile.get("preferences", {})
    return {
        "status": "ok",
        "profile": profile.get("profile", {}),
        "stats": {"total_preferences": len(prefs)}
    }


async def update_user_profile(
    preference_key: str,
    value: str,
    *,
    confidence: float = 1.0
) -> dict[str, object]:
    """Update the user profile with a new preference.

    Stores the preference in the profile's preferences dict with confidence
    metadata.

    Args:
        preference_key: Key for the preference (e.g. "coding_style").
        value: The preference value.
        confidence: Confidence level (0.0-1.0) for this preference.

    Returns:
        Dict with status and preference key.
    """
    profile = _load_profile()

    if "preferences" not in profile:
        profile["preferences"] = {}

    profile["preferences"][preference_key] = {
        "value": value,
        "confidence": confidence,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    _save_profile(profile)
    logger.info("User profile updated: %s = %r (confidence=%.2f)", preference_key, value, confidence)
    return {"status": "ok", "preference_key": preference_key}


def load_user_profile() -> dict[str, Any]:
    """Load the raw user profile data.

    Returns:
        Dict with preferences and profile data.
    """
    return _load_profile()


def save_user_profile(profile: dict[str, Any]) -> None:
    """Save user profile data.

    Args:
        profile: Profile data to save.
    """
    _save_profile(profile)


async def consolidate_memories(*, dry_run: bool = True) -> dict[str, object]:
    """Find and optionally merge duplicate or similar memories.

    Scans all memories and identifies potential duplicates based on
    key similarity and value overlap.

    Args:
        dry_run: If True, only report duplicates without merging.

    Returns:
        Dict with status, count of duplicates found, and actions taken.
    """
    data = _load_raw()
    entries = list(data.items())
    duplicates = []

    for i, (key1, entry1) in enumerate(entries):
        for key2, entry2 in entries[i+1:]:
            key1_norm = key1.lower().replace("_", " ").strip()
            key2_norm = key2.lower().replace("_", " ").strip()

            val1_words = set(entry1.value.lower().split())
            val2_words = set(entry2.value.lower().split())
            overlap = len(val1_words & val2_words) / max(len(val1_words), len(val2_words), 1)

            if key1_norm == key2_norm or overlap > 0.7:
                duplicates.append({
                    "keys": [key1, key2],
                    "reason": "key_match" if key1_norm == key2_norm else "value_overlap",
                    "overlap_score": round(overlap, 2)
                })

    actions = []
    if not dry_run and duplicates:
        actions.append("would_merge_duplicates")

    return {
        "status": "ok",
        "dry_run": dry_run,
        "duplicates_found": len(duplicates),
        "duplicates": duplicates,
        "actions": actions
    }


async def get_memory_stats() -> dict[str, object]:
    """Get statistics about the memory store.

    Returns summary statistics including total entries, counts by category,
    and memory access patterns.

    Returns:
        Dict with status and various memory statistics.
    """
    data = _load_raw()
    entries = list(data.values())

    if not entries:
        return {
            "status": "ok",
            "total_entries": 0,
            "by_category": {},
            "by_tag": {},
            "oldest_memory": None,
            "newest_memory": None
        }

    by_category = {}
    for entry in entries:
        by_category[entry.category] = by_category.get(entry.category, 0) + 1

    by_tag = {}
    for entry in entries:
        for tag in entry.tags:
            by_tag[tag] = by_tag.get(tag, 0) + 1

    timestamps = [e.created_at for e in entries]
    oldest = min(timestamps)
    newest = max(timestamps)

    return {
        "status": "ok",
        "total_entries": len(entries),
        "by_category": by_category,
        "by_tag": by_tag,
        "oldest_memory": oldest.isoformat(),
        "newest_memory": newest.isoformat()
    }
