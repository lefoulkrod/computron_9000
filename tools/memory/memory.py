"""Persistent key-value memory for COMPUTRON, stored in the app home directory.

This module implements a hierarchical memory system with three tiers:
- Semantic Memory: Long-term facts and user preferences
- Episodic Memory: Conversation summaries and interaction history  
- Working Memory: Session-specific, temporary data

Features:
- Fuzzy search using rapidfuzz for intelligent matching
- Category and tag-based filtering
- LRU caching for frequently accessed memories
- Backward compatibility with v1 memory format
"""

from __future__ import annotations

import json
import logging
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from config import load_config

logger = logging.getLogger(__name__)

# Try to import rapidfuzz for fuzzy matching, fall back to simple substring matching
try:
    from rapidfuzz import fuzz, process

    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    logger.warning("rapidfuzz not available, using simple substring matching for search")

# Storage format v2: {"key": {"value": "...", "hidden": false, "category": "...", "tags": [...], ...}}
# Storage format v1 (backward compatible): {"key": {"value": "...", "hidden": false}}


class MemoryCategory(Enum):
    """Categories for organizing memories hierarchically."""

    SEMANTIC = "semantic"  # Long-term facts, user preferences
    EPISODIC = "episodic"  # Conversation summaries, interaction history
    WORKING = "working"  # Session-specific temporary data


@dataclass
class MemoryEntry:
    """A single stored memory with metadata.

    Attributes:
        value: The stored memory value
        hidden: Whether the memory is hidden from UI
        category: Memory category (semantic, episodic, working)
        tags: List of searchable tags
        confidence: Confidence score (0.0-1.0)
        created_at: Unix timestamp when memory was created
        accessed_at: Unix timestamp of last access
        access_count: Number of times this memory has been accessed
    """

    value: str
    hidden: bool = False
    category: MemoryCategory = MemoryCategory.SEMANTIC
    tags: list[str] = field(default_factory=list)
    confidence: float = 1.0
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    access_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize memory entry to dictionary."""
        return {
            "value": self.value,
            "hidden": self.hidden,
            "category": self.category.value,
            "tags": self.tags,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "accessed_at": self.accessed_at,
            "access_count": self.access_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryEntry":
        """Deserialize memory entry from dictionary."""
        # Handle v1 format migration
        if "category" not in data:
            return cls(
                value=str(data["value"]),
                hidden=bool(data.get("hidden", False)),
            )

        return cls(
            value=str(data["value"]),
            hidden=bool(data.get("hidden", False)),
            category=MemoryCategory(data.get("category", "semantic")),
            tags=list(data.get("tags", [])),
            confidence=float(data.get("confidence", 1.0)),
            created_at=float(data.get("created_at", time.time())),
            accessed_at=float(data.get("accessed_at", time.time())),
            access_count=int(data.get("access_count", 0)),
        )


# Simple LRU cache for memory access
_memory_cache: dict[str, MemoryEntry] = {}
_cache_keys: list[str] = []
_MAX_CACHE_SIZE = 1000


def _get_cache(key: str) -> MemoryEntry | None:
    """Get entry from cache if present."""
    if key in _memory_cache:
        # Move to end (most recently used)
        _cache_keys.remove(key)
        _cache_keys.append(key)
        return _memory_cache[key]
    return None


def _set_cache(key: str, entry: MemoryEntry) -> None:
    """Add entry to cache, evicting oldest if necessary."""
    global _cache_keys, _memory_cache

    if key in _memory_cache:
        _cache_keys.remove(key)
    elif len(_cache_keys) >= _MAX_CACHE_SIZE:
        # Evict oldest
        oldest = _cache_keys.pop(0)
        del _memory_cache[oldest]

    _cache_keys.append(key)
    _memory_cache[key] = entry


def _reset_cache() -> None:
    """Clear the memory cache."""
    global _cache_keys, _memory_cache
    _cache_keys = []
    _memory_cache = {}


def _memory_path() -> Path:
    """Get the path to the memory storage file."""
    return Path(load_config().settings.home_dir) / "memory.json"


def _load_raw() -> dict[str, MemoryEntry]:
    """Load all memories from disk."""
    path = _memory_path()
    if not path.exists():
        return {}
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return {k: MemoryEntry.from_dict(v) for k, v in data.items()}
    except Exception:
        logger.exception("Failed to load memory from %s", path)
        return {}


def _save_raw(data: dict[str, MemoryEntry]) -> None:
    """Save all memories to disk."""
    path = _memory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = {k: e.to_dict() for k, e in data.items()}
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, delete=False, suffix=".tmp", encoding="utf-8"
    ) as f:
        json.dump(serialized, f, indent=2, ensure_ascii=False)
        tmp = Path(f.name)
    tmp.replace(path)


def load_memory(category: MemoryCategory | None = None) -> dict[str, MemoryEntry]:
    """Load all stored memories, optionally filtered by category.

    Args:
        category: Optional category filter

    Returns:
        Dictionary of memory entries
    """
    data = _load_raw()
    if category:
        return {k: v for k, v in data.items() if v.category == category}
    return data


def set_key_hidden(key: str, hidden: bool) -> None:
    """Mark a memory key as hidden or visible in the UI."""
    data = _load_raw()
    if key in data:
        data[key].hidden = hidden
        _save_raw(data)
        _set_cache(key, data[key])


def get_memory(key: str) -> MemoryEntry | None:
    """Retrieve a single memory by key, updating access metadata.

    Args:
        key: Memory key to retrieve

    Returns:
        Memory entry if found, None otherwise
    """
    # Check cache first
    cached = _get_cache(key)
    if cached:
        cached.access_count += 1
        cached.accessed_at = time.time()
        return cached

    data = _load_raw()
    if key in data:
        entry = data[key]
        entry.access_count += 1
        entry.accessed_at = time.time()
        _save_raw(data)
        _set_cache(key, entry)
        return entry
    return None


async def remember(
    key: str,
    value: str,
    category: str = "semantic",
    tags: list[str] | None = None,
    confidence: float = 1.0,
) -> dict[str, object]:
    """Store a persistent memory that will be available in all future sessions.

    Use this to remember facts about the user, their preferences, useful context,
    or anything worth recalling later. Memories persist indefinitely.

    Args:
        key: Short identifier for the memory (e.g. "user_timezone", "preferred_language").
        value: The value to remember.
        category: Memory category - "semantic" (facts/preferences), "episodic" (conversation),
                 or "working" (session data). Defaults to "semantic".
        tags: Optional list of searchable tags for categorization.
        confidence: Confidence score 0.0-1.0 for the memory's reliability.

    Returns:
        Confirmation dict with status and stored key/value.
    """
    data = _load_raw()

    # Parse category
    try:
        mem_category = MemoryCategory(category.lower())
    except ValueError:
        mem_category = MemoryCategory.SEMANTIC

    # preserve existing hidden state and metadata when updating a key
    existing = data.get(key)
    if existing:
        entry = MemoryEntry(
            value=value,
            hidden=existing.hidden,
            category=mem_category,
            tags=tags or existing.tags,
            confidence=confidence,
            created_at=existing.created_at,
            accessed_at=time.time(),
            access_count=existing.access_count,
        )
    else:
        entry = MemoryEntry(
            value=value,
            category=mem_category,
            tags=tags or [],
            confidence=confidence,
        )

    data[key] = entry
    _save_raw(data)
    _set_cache(key, entry)
    logger.info("Memory stored: %s = %r (category=%s)", key, value, category)
    return {
        "status": "ok",
        "key": key,
        "value": value,
        "category": category,
        "tags": entry.tags,
    }


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
    # Remove from cache
    if key in _memory_cache:
        del _memory_cache[key]
        _cache_keys.remove(key)
    logger.info("Memory forgotten: %s", key)
    return {"status": "ok", "key": key}


async def search_memories(
    query: str,
    limit: int = 10,
    category: str | None = None,
    tags: list[str] | None = None,
    min_confidence: float = 0.0,
) -> dict[str, object]:
    """Search memories using fuzzy matching on keys and values.

    Args:
        query: Search query string
        limit: Maximum number of results to return
        category: Optional category filter ("semantic", "episodic", "working")
        tags: Optional list of tags to filter by (memories must have at least one)
        min_confidence: Minimum confidence score (0.0-1.0)

    Returns:
        Dictionary with matching memories sorted by relevance
    """
    data = _load_raw()

    # Filter by category if specified
    if category:
        try:
            cat_filter = MemoryCategory(category.lower())
            data = {k: v for k, v in data.items() if v.category == cat_filter}
        except ValueError:
            pass

    # Filter by tags if specified
    if tags:
        data = {
            k: v
            for k, v in data.items()
            if any(tag in v.tags for tag in tags)
        }

    # Filter by confidence
    data = {k: v for k, v in data.items() if v.confidence >= min_confidence}

    if not data:
        return {"status": "ok", "query": query, "results": [], "count": 0}

    # Perform fuzzy search
    if RAPIDFUZZ_AVAILABLE:
        # Combine keys and values for searching
        search_items = [(k, f"{k} {v.value}") for k, v in data.items()]
        results = process.extract(query, search_items, processor=lambda x: x[1], limit=limit)

        matches = []
        for match in results:
            item = match[0]
            score = match[1]
            key = item[0]
            entry = data[key]
            matches.append(
                {
                    "key": key,
                    "value": entry.value,
                    "category": entry.category.value,
                    "tags": entry.tags,
                    "confidence": entry.confidence,
                    "score": score / 100.0,  # Normalize to 0-1
                    "access_count": entry.access_count,
                    "last_accessed": entry.accessed_at,
                }
            )
    else:
        # Simple substring fallback
        query_lower = query.lower()
        matches = []
        for key, entry in data.items():
            score = 0.0
            if query_lower in key.lower():
                score += 0.5
            if query_lower in entry.value.lower():
                score += 0.5
            if score > 0:
                matches.append(
                    {
                        "key": key,
                        "value": entry.value,
                        "category": entry.category.value,
                        "tags": entry.tags,
                        "confidence": entry.confidence,
                        "score": score,
                        "access_count": entry.access_count,
                        "last_accessed": entry.accessed_at,
                    }
                )
        matches.sort(key=lambda x: x["score"], reverse=True)
        matches = matches[:limit]

    return {"status": "ok", "query": query, "results": matches, "count": len(matches)}


async def query_memories(
    tags: list[str] | None = None,
    category: str | None = None,
    created_after: float | None = None,
    created_before: float | None = None,
    min_confidence: float | None = None,
    limit: int = 100,
) -> dict[str, object]:
    """Query memories with structured filters.

    Args:
        tags: List of tags to filter by (memories must have at least one)
        category: Category to filter by
        created_after: Unix timestamp - only memories created after this time
        created_before: Unix timestamp - only memories created before this time
        min_confidence: Minimum confidence score
        limit: Maximum number of results

    Returns:
        Dictionary with filtered memories
    """
    data = _load_raw()
    results = []

    for key, entry in data.items():
        # Apply filters
        if category and entry.category.value != category.lower():
            continue
        if tags and not any(tag in entry.tags for tag in tags):
            continue
        if created_after and entry.created_at < created_after:
            continue
        if created_before and entry.created_at > created_before:
            continue
        if min_confidence is not None and entry.confidence < min_confidence:
            continue

        results.append(
            {
                "key": key,
                "value": entry.value,
                "category": entry.category.value,
                "tags": entry.tags,
                "confidence": entry.confidence,
                "created_at": entry.created_at,
                "accessed_at": entry.accessed_at,
                "access_count": entry.access_count,
            }
        )

        if len(results) >= limit:
            break

    return {"status": "ok", "results": results, "count": len(results)}


async def get_related_memories(
    key: str,
    limit: int = 5,
) -> dict[str, object]:
    """Get memories related to a given key based on shared tags and category.

    Args:
        key: The reference memory key
        limit: Maximum number of related memories to return

    Returns:
        Dictionary with related memories
    """
    entry = get_memory(key)
    if not entry:
        return {"status": "not_found", "key": key, "results": []}

    data = _load_raw()
    related = []

    for other_key, other_entry in data.items():
        if other_key == key:
            continue

        # Calculate relevance score
        score = 0
        if other_entry.category == entry.category:
            score += 1
        shared_tags = set(other_entry.tags) & set(entry.tags)
        score += len(shared_tags)

        if score > 0:
            related.append(
                {
                    "key": other_key,
                    "value": other_entry.value,
                    "category": other_entry.category.value,
                    "shared_tags": list(shared_tags),
                    "relevance_score": score,
                }
            )

    # Sort by relevance
    related.sort(key=lambda x: x["relevance_score"], reverse=True)
    related = related[:limit]

    return {"status": "ok", "key": key, "results": related, "count": len(related)}


async def get_memory_stats() -> dict[str, object]:
    """Get statistics about the memory system.

    Returns:
        Dictionary with memory statistics
    """
    data = _load_raw()

    total = len(data)
    by_category = {cat.value: 0 for cat in MemoryCategory}
    for entry in data.values():
        by_category[entry.category.value] += 1

    total_accesses = sum(e.access_count for e in data.values())
    avg_confidence = sum(e.confidence for e in data.values()) / total if total > 0 else 0

    # Get most accessed memories
    most_accessed = sorted(
        [(k, e.access_count) for k, e in data.items()],
        key=lambda x: x[1],
        reverse=True,
    )[:5]

    return {
        "status": "ok",
        "total_memories": total,
        "by_category": by_category,
        "total_accesses": total_accesses,
        "average_confidence": round(avg_confidence, 2),
        "most_accessed": [{"key": k, "access_count": c} for k, c in most_accessed],
    }


async def update_memory_tags(
    key: str,
    add_tags: list[str] | None = None,
    remove_tags: list[str] | None = None,
) -> dict[str, object]:
    """Update tags for a memory entry.

    Args:
        key: Memory key to update
        add_tags: Tags to add
        remove_tags: Tags to remove

    Returns:
        Updated memory entry
    """
    data = _load_raw()
    if key not in data:
        return {"status": "not_found", "key": key}

    entry = data[key]
    current_tags = set(entry.tags)

    if add_tags:
        current_tags.update(add_tags)
    if remove_tags:
        current_tags.difference_update(remove_tags)

    entry.tags = list(current_tags)
    _save_raw(data)
    _set_cache(key, entry)

    return {
        "status": "ok",
        "key": key,
        "tags": entry.tags,
        "category": entry.category.value,
    }


async def consolidate_memories(
    keys: list[str],
    new_key: str,
    new_value: str | None = None,
    category: str | None = None,
) -> dict[str, object]:
    """Consolidate multiple memories into a single new memory.

    Args:
        keys: List of memory keys to consolidate
        new_key: Key for the consolidated memory
        new_value: Optional new value (combines old values if not provided)
        new_category: Optional category for the consolidated memory

    Returns:
        Result of the consolidation
    """
    data = _load_raw()

    entries = []
    for key in keys:
        if key in data:
            entries.append(data[key])

    if not entries:
        return {"status": "error", "message": "No valid memories found to consolidate"}

    # Combine values if new value not provided
    if new_value is None:
        new_value = " | ".join(e.value for e in entries)

    # Determine category
    if category:
        try:
            new_category = MemoryCategory(category.lower())
        except ValueError:
            new_category = entries[0].category
    else:
        new_category = entries[0].category

    # Combine tags
    all_tags = set()
    for e in entries:
        all_tags.update(e.tags)

    # Create consolidated entry
    consolidated = MemoryEntry(
        value=new_value,
        category=new_category,
        tags=list(all_tags),
        confidence=min(e.confidence for e in entries),
    )

    # Remove old entries
    for key in keys:
        if key in data:
            del data[key]
            if key in _memory_cache:
                del _memory_cache[key]
                _cache_keys.remove(key)

    # Add new entry
    data[new_key] = consolidated
    _save_raw(data)
    _set_cache(new_key, consolidated)

    return {
        "status": "ok",
        "consolidated_key": new_key,
        "source_keys": keys,
        "category": new_category.value,
        "tags": list(all_tags),
    }
