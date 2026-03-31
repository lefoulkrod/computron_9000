"""Enhanced multi-indexed memory system with semantic and temporal queries.

This module extends the basic memory system with:
- Timestamps (created_at, updated_at)
- Semantic embeddings for content similarity search
- Auto-extracted tags from content
- Multiple query strategies (key, semantic, timeframe, hybrid)
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from .memory import MemoryEntry, _memory_path

logger = logging.getLogger(__name__)

# Storage format version for migration handling
STORAGE_VERSION = "2.0"

# Common words to exclude from auto-tag extraction
STOP_WORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "can",
        "this",
        "that",
        "these",
        "those",
        "i",
        "you",
        "he",
        "she",
        "it",
        "we",
        "they",
        "me",
        "him",
        "her",
        "us",
        "them",
        "my",
        "your",
        "his",
        "its",
        "our",
        "their",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "up",
        "about",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "among",
        "within",
        "without",
    }
)


def _extract_tags(content: str, max_tags: int = 5) -> list[str]:
    """Extract meaningful tags from memory content.

    Tags are extracted by:
    1. Finding capitalized words/phrases (proper nouns)
    2. Finding words that appear to be technical terms (CamelCase, snake_case)
    3. Finding words that appear multiple times
    4. Filtering out stop words

    Args:
        content: The memory content to analyze.
        max_tags: Maximum number of tags to return.

    Returns:
        List of extracted tags, sorted by relevance.
    """
    # Normalize content
    text = content.lower()

    # Find all words
    words = re.findall(r"\b[a-z]+\b", text)

    # Count word frequencies (excluding stop words)
    word_counts: dict[str, int] = {}
    for word in words:
        if word not in STOP_WORDS and len(word) > 2:
            word_counts[word] = word_counts.get(word, 0) + 1

    # Find technical terms (CamelCase, snake_case in original)
    technical_terms = re.findall(r"\b[A-Z][a-z]+[A-Z][a-zA-Z]*\b", content)  # CamelCase
    technical_terms += re.findall(r"\b[a-z]+_[a-z_]+\b", content)  # snake_case

    # Find proper nouns (capitalized words in original)
    proper_nouns = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", content)

    # Score tags
    tag_scores: dict[str, float] = {}

    # Score by frequency
    for word, count in word_counts.items():
        tag_scores[word] = count * 1.0

    # Boost technical terms
    for term in technical_terms:
        term_lower = term.lower()
        tag_scores[term_lower] = tag_scores.get(term_lower, 0) + 3.0

    # Boost proper nouns
    for noun in proper_nouns:
        noun_lower = noun.lower()
        tag_scores[noun_lower] = tag_scores.get(noun_lower, 0) + 2.0

    # Sort by score and return top tags
    sorted_tags = sorted(tag_scores.items(), key=lambda x: x[1], reverse=True)
    return [tag for tag, _ in sorted_tags[:max_tags]]


def _compute_embedding(content: str) -> list[float]:
    """Compute a simple semantic embedding for content using TF-IDF.

    This is a lightweight embedding that doesn't require external models.
    For production use, consider integrating with sentence-transformers.

    Args:
        content: The text to embed.

    Returns:
        Vector representation as a list of floats.
    """
    # Simple character n-gram based embedding as fallback
    # This creates a fixed-size vector based on character distributions
    vector_size = 128
    embedding = np.zeros(vector_size, dtype=np.float32)

    # Add character n-gram features (2-grams)
    text = content.lower()
    for i in range(len(text) - 1):
        bigram = text[i : i + 2]
        # Hash to index
        idx = hash(bigram) % vector_size
        embedding[idx] += 1.0

    # Normalize
    norm = np.linalg.norm(embedding)
    if norm > 0:
        embedding = embedding / norm

    return embedding.tolist()


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        vec1: First vector.
        vec2: Second vector.

    Returns:
        Cosine similarity score (0.0 to 1.0).
    """
    a = np.array(vec1)
    b = np.array(vec2)

    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(np.dot(a, b) / (norm_a * norm_b))


@dataclass
class EnhancedMemoryEntry:
    """Enhanced memory entry with metadata for multi-indexed retrieval.

    Attributes:
        value: The memory content.
        hidden: Whether this memory is hidden from UI.
        created_at: Timestamp when memory was first created.
        updated_at: Timestamp when memory was last updated.
        tags: Auto-extracted tags from content.
        embedding: Semantic embedding vector for similarity search.
        version: Storage format version for migrations.
    """

    value: str
    hidden: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    tags: list[str] = field(default_factory=list)
    embedding: list[float] = field(default_factory=list)
    version: str = STORAGE_VERSION

    @classmethod
    def from_basic(cls, entry: MemoryEntry, key: str = "") -> EnhancedMemoryEntry:
        """Convert a basic MemoryEntry to enhanced format.

        Args:
            entry: The basic memory entry to enhance.
            key: Optional key for tag extraction context.

        Returns:
            Enhanced memory entry with computed metadata.
        """
        now = datetime.now().isoformat()
        content = entry.value

        # Extract tags from content
        tags = _extract_tags(content)

        # Compute embedding
        embedding = _compute_embedding(content)

        return cls(
            value=entry.value,
            hidden=entry.hidden,
            created_at=now,
            updated_at=now,
            tags=tags,
            embedding=embedding,
            version=STORAGE_VERSION,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "value": self.value,
            "hidden": self.hidden,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags,
            "embedding": self.embedding,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnhancedMemoryEntry:
        """Create from dictionary (handles migration from old format)."""
        version = data.get("version", "1.0")

        if version == "1.0":
            # Migrate from basic format
            entry = MemoryEntry(value=data["value"], hidden=data.get("hidden", False))
            enhanced = cls.from_basic(entry)
            # Use current time for migrated entries
            return enhanced

        return cls(
            value=data["value"],
            hidden=data.get("hidden", False),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            tags=data.get("tags", []),
            embedding=data.get("embedding", []),
            version=version,
        )


def _load_enhanced_raw() -> dict[str, EnhancedMemoryEntry]:
    """Load all memories in enhanced format (with migration support)."""
    path = _memory_path()
    if not path.exists():
        return {}

    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        result: dict[str, EnhancedMemoryEntry] = {}
        migrated = False

        for key, value in data.items():
            if isinstance(value, dict):
                entry = EnhancedMemoryEntry.from_dict(value)
                # Check if this was a migration
                if entry.version == "1.0" or "version" not in value:
                    migrated = True
                result[key] = entry
            else:
                # Handle legacy format where value was just a string
                entry = EnhancedMemoryEntry.from_basic(MemoryEntry(value=str(value), hidden=False), key)
                migrated = True
                result[key] = entry

        if migrated:
            # Save back in new format
            _save_enhanced_raw(result)
            logger.info("Migrated memory storage to enhanced format")

        return result
    except Exception:
        logger.exception("Failed to load enhanced memory from %s", path)
        return {}


def _save_enhanced_raw(data: dict[str, EnhancedMemoryEntry]) -> None:
    """Save memories in enhanced format."""
    path = _memory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = {k: e.to_dict() for k, e in data.items()}

    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, suffix=".tmp", encoding="utf-8") as f:
        json.dump(serialized, f, indent=2, ensure_ascii=False)
        tmp = Path(f.name)
    tmp.replace(path)


async def remember_enhanced(key: str, value: str, hidden: str = "false") -> dict[str, object]:
    """Store a memory with enhanced metadata (timestamps, tags, embeddings).

    This extends the basic remember function with automatic metadata extraction:
    - Timestamps for temporal queries
    - Auto-extracted tags for categorical queries
    - Semantic embeddings for similarity search

    Args:
        key: Short identifier for the memory.
        value: The content to remember.
        hidden: If "true", mark as hidden from UI.

    Returns:
        Confirmation dict with stored metadata.
    """
    is_hidden = hidden.lower() in ("true", "1", "yes")

    data = _load_enhanced_raw()

    now = datetime.now().isoformat()

    if key in data:
        # Update existing entry, preserve created_at
        existing = data[key]
        entry = EnhancedMemoryEntry(
            value=value,
            hidden=is_hidden,
            created_at=existing.created_at,
            updated_at=now,
            tags=_extract_tags(value),
            embedding=_compute_embedding(value),
            version=STORAGE_VERSION,
        )
    else:
        # Create new entry
        entry = EnhancedMemoryEntry.from_basic(MemoryEntry(value=value, hidden=is_hidden), key)

    data[key] = entry
    _save_enhanced_raw(data)

    logger.info("Enhanced memory stored: %s (tags: %r)", key, entry.tags)

    return {
        "status": "ok",
        "key": key,
        "value": value,
        "tags": entry.tags,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


async def query_memory_by_key(key: str) -> dict[str, object]:
    """Query memory by exact key lookup.

    Args:
        key: The exact memory key to retrieve.

    Returns:
        Dict with memory entry and metadata, or not_found status.
    """
    data = _load_enhanced_raw()

    if key not in data:
        return {"status": "not_found", "key": key}

    entry = data[key]

    return {
        "status": "ok",
        "key": key,
        "value": entry.value,
        "hidden": entry.hidden,
        "tags": entry.tags,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


async def query_memory_by_semantic(query: str, top_k: str = "5", threshold: str = "0.5") -> dict[str, object]:
    """Query memories by semantic similarity to the query text.

    Uses cosine similarity on pre-computed embeddings to find memories
    with similar meaning to the query.

    Args:
        query: The text to search for semantically.
        top_k: Maximum number of results to return (default: 5).
        threshold: Minimum similarity threshold 0.0-1.0 (default: 0.5).

    Returns:
        Dict with list of matching memories ranked by similarity.
    """
    try:
        k = int(top_k)
        thresh = float(threshold)
    except ValueError:
        return {"status": "error", "message": "Invalid top_k or threshold value"}

    data = _load_enhanced_raw()

    if not data:
        return {"status": "ok", "results": [], "count": 0}

    # Compute query embedding
    query_embedding = _compute_embedding(query)

    # Score all memories by similarity
    scored_results: list[tuple[str, EnhancedMemoryEntry, float]] = []
    for key, entry in data.items():
        if entry.hidden:
            continue

        if entry.embedding:
            similarity = _cosine_similarity(query_embedding, entry.embedding)
        else:
            # Fallback: compute embedding on the fly
            entry_embedding = _compute_embedding(entry.value)
            similarity = _cosine_similarity(query_embedding, entry_embedding)

        if similarity >= thresh:
            scored_results.append((key, entry, similarity))

    # Sort by similarity (descending)
    scored_results.sort(key=lambda x: x[2], reverse=True)

    # Take top_k
    top_results = scored_results[:k]

    results = [
        {
            "key": key,
            "value": entry.value,
            "similarity": round(score, 4),
            "tags": entry.tags,
            "created_at": entry.created_at,
        }
        for key, entry, score in top_results
    ]

    logger.info("Semantic query '%s...' returned %d results", query[:30], len(results))

    return {"status": "ok", "query": query, "results": results, "count": len(results)}


async def query_memory_by_timeframe(timeframe: str, query_type: str = "created") -> dict[str, object]:
    """Query memories by temporal criteria.

    Supports natural language timeframes like "last week", "in January",
    "yesterday", "past 3 days", etc.

    Args:
        timeframe: Natural language timeframe specification.
        query_type: Which timestamp to query - "created", "updated", or "both".

    Returns:
        Dict with memories that fall within the specified timeframe.
    """
    data = _load_enhanced_raw()

    if not data:
        return {"status": "ok", "results": [], "count": 0}

    # Parse timeframe into datetime range
    now = datetime.now()
    start_time: datetime | None = None
    end_time: datetime | None = None

    timeframe_lower = timeframe.lower().strip()

    # Handle "last X units" patterns
    last_match = re.match(r"last\s+(\d+)\s+(day|days|week|weeks|month|months|year|years)", timeframe_lower)
    if last_match:
        count = int(last_match.group(1))
        unit = last_match.group(2)

        if unit in ("day", "days"):
            start_time = now - timedelta(days=count)
        elif unit in ("week", "weeks"):
            start_time = now - timedelta(weeks=count)
        elif unit in ("month", "months"):
            start_time = now - timedelta(days=count * 30)  # Approximate
        elif unit in ("year", "years"):
            start_time = now - timedelta(days=count * 365)  # Approximate
        end_time = now

    # Handle "past X units" (same as last)
    elif re.match(r"past\s+(\d+)", timeframe_lower):
        # Reuse last logic
        return await query_memory_by_timeframe(timeframe_lower.replace("past", "last", 1), query_type)

    # Handle "yesterday"
    elif timeframe_lower in ("yesterday", "yester day"):
        start_time = now - timedelta(days=1)
        end_time = now
        # More precise: yesterday's date only
        yesterday = now - timedelta(days=1)
        start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Handle "today"
    elif timeframe_lower == "today":
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = now

    # Handle "this week"
    elif timeframe_lower == "this week":
        start_time = now - timedelta(days=now.weekday())
        start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = now

    # Handle "this month"
    elif timeframe_lower == "this month":
        start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_time = now

    # Handle "in January", "in February", etc.
    elif re.match(
        r"in\s+(january|february|march|april|may|june|july|august|september|october|november|december)", timeframe_lower
    ):
        month_names = [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ]
        match = re.search(
            r"(january|february|march|april|may|june|july|august|september|october|november|december)", timeframe_lower
        )
        if match:
            month_idx = month_names.index(match.group(1))
            # Assume current year, but could be last year if month > current
            year = now.year
            if month_idx > now.month - 1:
                year -= 1
            start_time = datetime(year, month_idx + 1, 1)
            if month_idx == 11:
                end_time = datetime(year + 1, 1, 1) - timedelta(microseconds=1)
            else:
                end_time = datetime(year, month_idx + 2, 1) - timedelta(microseconds=1)

    # Handle "last week", "last month", "last year"
    elif timeframe_lower == "last week":
        last_week_start = now - timedelta(weeks=1, days=now.weekday())
        start_time = last_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(days=6, hours=23, minutes=59, seconds=59)
    elif timeframe_lower == "last month":
        start_time = datetime(now.year - 1, 12, 1) if now.month == 1 else datetime(now.year, now.month - 1, 1)
        end_time = datetime(now.year, now.month, 1) - timedelta(microseconds=1)
    elif timeframe_lower == "last year":
        start_time = datetime(now.year - 1, 1, 1)
        end_time = datetime(now.year, 1, 1) - timedelta(microseconds=1)

    # Handle "recent" (last 7 days)
    elif timeframe_lower in ("recent", "lately"):
        start_time = now - timedelta(days=7)
        end_time = now

    else:
        return {
            "status": "error",
            "message": (
                "Unrecognized timeframe format. Try: 'last week', 'past 3 days', 'in January', 'yesterday', 'today'"
            ),
        }

    # Filter memories
    results: list[dict[str, object]] = []

    for key, entry in data.items():
        if entry.hidden:
            continue

        try:
            if query_type in ("created", "both"):
                created_dt = datetime.fromisoformat(entry.created_at)
                if start_time and end_time and start_time <= created_dt <= end_time:
                    results.append(
                        {
                            "key": key,
                            "value": entry.value,
                            "timestamp": entry.created_at,
                            "timestamp_type": "created",
                            "tags": entry.tags,
                        }
                    )
                    continue

            if query_type in ("updated", "both"):
                updated_dt = datetime.fromisoformat(entry.updated_at)
                if start_time and end_time and start_time <= updated_dt <= end_time:
                    results.append(
                        {
                            "key": key,
                            "value": entry.value,
                            "timestamp": entry.updated_at,
                            "timestamp_type": "updated",
                            "tags": entry.tags,
                        }
                    )
        except ValueError:
            # Skip entries with invalid timestamps
            continue

    # Sort by timestamp (newest first)
    results.sort(key=lambda x: x["timestamp"], reverse=True)

    logger.info("Timeframe query '%s' returned %d results", timeframe, len(results))

    return {"status": "ok", "timeframe": timeframe, "results": results, "count": len(results)}


async def query_memory_smart(query: str, context: str = "") -> dict[str, object]:
    """Smart memory query that automatically selects the best query strategy.

    Analyzes the query to determine which retrieval method(s) to use:
    - Exact key patterns (e.g., "user_preference") → key lookup
    - Time phrases (e.g., "last week", "in January") → timeframe query
    - Descriptive text → semantic similarity
    - Ambiguous queries → combines multiple strategies

    Args:
        query: The user's memory query.
        context: Optional context to help disambiguate query intent.

    Returns:
        Dict with ranked results from the most appropriate query strategy(s).
    """
    data = _load_enhanced_raw()

    if not data:
        return {"status": "ok", "results": [], "count": 0, "strategy": "none"}

    query_lower = query.lower().strip()
    strategies_used: list[str] = []
    all_results: list[dict[str, object]] = []

    # Strategy 1: Check for exact key match
    # Pattern: single word without spaces, or quoted key
    key_pattern = re.match(r'^["\']?([a-z_]+)["\']?$', query_lower)
    if key_pattern:
        potential_key = key_pattern.group(1)
        if potential_key in data:
            entry = data[potential_key]
            if not entry.hidden:
                all_results.append(
                    {
                        "key": potential_key,
                        "value": entry.value,
                        "match_type": "exact_key",
                        "score": 1.0,
                        "tags": entry.tags,
                        "created_at": entry.created_at,
                    }
                )
                strategies_used.append("key")

    # Strategy 2: Check for time-based queries
    time_patterns = [
        r"\blast\s+\w+",
        r"\bpast\s+\d+",
        r"\byesterday\b",
        r"\btoday\b",
        r"\brecent\b",
        r"\bin\s+(january|february|march|april|may|june|july|august|september|october|november|december)",
        r"\bthis\s+(week|month|year)\b",
    ]

    is_time_query = any(re.search(pattern, query_lower) for pattern in time_patterns)

    if is_time_query:
        # Extract timeframe portion
        timeframe_result = await query_memory_by_timeframe(query, "both")
        if timeframe_result["status"] == "ok":
            for result in timeframe_result["results"]:
                result["match_type"] = "timeframe"
                result["score"] = 0.8  # Good confidence for timeframe matches
                all_results.append(result)
            strategies_used.append("timeframe")

    # Strategy 3: Semantic search (always run for text queries)
    # Skip if we already have exact key match and query is short
    if len(query) > 3 and (not strategies_used or len(all_results) < 3):
        semantic_result = await query_memory_by_semantic(query, top_k="10", threshold="0.3")
        if semantic_result["status"] == "ok":
            for result in semantic_result["results"]:
                # Avoid duplicates from key match
                existing_keys = {r["key"] for r in all_results}
                if result["key"] not in existing_keys:
                    result["match_type"] = "semantic"
                    result["score"] = result.get("similarity", 0.5)
                    all_results.append(result)
            strategies_used.append("semantic")

    # Strategy 4: Check for tag matches
    query_words = set(re.findall(r"\b\w+\b", query_lower))
    for key, entry in data.items():
        if entry.hidden:
            continue

        entry_tags = {tag.lower() for tag in entry.tags}
        matching_tags = query_words & entry_tags

        if matching_tags:
            # Check if not already in results
            existing = next((r for r in all_results if r["key"] == key), None)
            if existing:
                # Boost score for tag match
                existing["score"] = max(existing.get("score", 0), 0.7)
                existing["matching_tags"] = list(matching_tags)
            else:
                all_results.append(
                    {
                        "key": key,
                        "value": entry.value,
                        "match_type": "tag",
                        "score": 0.6 + (0.1 * len(matching_tags)),
                        "matching_tags": list(matching_tags),
                        "tags": entry.tags,
                        "created_at": entry.created_at,
                    }
                )

    if "tag" not in strategies_used and any(r.get("match_type") == "tag" for r in all_results):
        strategies_used.append("tag")

    # Deduplicate and sort by score
    seen_keys: set[str] = set()
    unique_results: list[dict[str, object]] = []

    # Sort by score descending
    all_results.sort(key=lambda x: x.get("score", 0), reverse=True)

    for result in all_results:
        key = result["key"]
        if key not in seen_keys:
            seen_keys.add(key)
            unique_results.append(result)

    # Limit results
    final_results = unique_results[:10]

    logger.info(
        "Smart query '%s...' used strategies %r, returned %d results", query[:30], strategies_used, len(final_results)
    )

    return {
        "status": "ok",
        "query": query,
        "strategies": strategies_used if strategies_used else ["semantic"],
        "results": final_results,
        "count": len(final_results),
    }
