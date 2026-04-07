"""Persistent key-value memory tools for COMPUTRON.

This module provides a hierarchical memory system with three tiers:
- Semantic Memory: Long-term facts and user preferences
- Episodic Memory: Conversation summaries and interaction history
- Working Memory: Session-specific, temporary data

Key Features:
- Fuzzy search with rapidfuzz
- Category and tag-based filtering
- LRU caching for performance
- Structured queries with date ranges and confidence scores
- Memory consolidation and relationship detection
"""

from .memory import (
    MemoryCategory,
    MemoryEntry,
    consolidate_memories,
    forget,
    get_memory,
    get_memory_stats,
    get_related_memories,
    load_memory,
    query_memories,
    remember,
    search_memories,
    set_key_hidden,
    update_memory_tags,
)

__all__ = [
    "MemoryCategory",
    "MemoryEntry",
    "consolidate_memories",
    "forget",
    "get_memory",
    "get_memory_stats",
    "get_related_memories",
    "load_memory",
    "query_memories",
    "remember",
    "search_memories",
    "set_key_hidden",
    "update_memory_tags",
]
