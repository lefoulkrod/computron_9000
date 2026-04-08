# Semantic Memory Store with Profile-Based Personalization - Implementation Plan

## Overview

This implementation plan details the construction of a semantic memory system for computron_9000 that enables:
1. **Semantic search** - Find memories by meaning, not just exact keyword matches
2. **User profiling** - Store structured user preferences with confidence scores
3. **Memory categorization** - Organize memories by type (preferences, technical facts, projects, etc.)
4. **Access tracking** - Frequently used memories rank higher
5. **Memory consolidation** - Identify and merge duplicate memories

## Architecture

### Data Models

#### MemoryEntry
A dataclass representing a single memory with rich metadata:

```python
@dataclass
class MemoryEntry:
    value: str                          # The stored value
    hidden: bool = False                # Visibility in UI
    category: str = "user_preference"   # Memory category
    tags: list[str] = []                # Searchable tags
    created_at: datetime                # Creation timestamp
    updated_at: datetime                # Last modification
    access_count: int = 0               # Access frequency
```

#### MemoryCategory (Constants)
- `USER_PREFERENCE` - User likes/dislikes
- `TECHNICAL_FACT` - Technical knowledge about user
- `PROJECT_CONTEXT` - Current project information
- `CONVERSATION_SUMMARY` - Key conversation points
- `GOAL` - User goals
- `HABIT` - Recurring patterns
- `PERSONAL_INFO` - Personal details
- `GENERAL` - Uncategorized

#### User Profile Structure
```json
{
  "preferences": {
    "coding_style": {
      "value": "concise",
      "confidence": 0.9,
      "updated_at": "2024-01-15T10:30:00"
    }
  },
  "profile": {}
}
```

### Storage

**Memory storage**: `~/.computron_9000/memory.json` (JSON file, atomic writes via temp+rename)
**Profile storage**: `~/.computron_9000/user_profile.json` (JSON file, atomic writes)

## Implementation Steps

### Step 1: Create MemoryEntry Dataclass and MemoryCategory Constants

**File**: `tools/memory/memory.py`

```python
class MemoryCategory:
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
    value: str
    hidden: bool = False
    category: str = MemoryCategory.USER_PREFERENCE
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = field(default_factory=lambda: datetime.utcnow())
    access_count: int = 0

    def to_dict(self) -> dict[str, Any]:
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
        return cls(
            value=str(data.get("value", "")),
            hidden=bool(data.get("hidden", False)),
            category=str(data.get("category", MemoryCategory.USER_PREFERENCE)),
            tags=list(data.get("tags", [])),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.utcnow(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.utcnow(),
            access_count=int(data.get("access_count", 0)),
        )
```

### Step 2: Implement Storage Functions

**File**: `tools/memory/memory.py`

```python
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
        return {
            k: MemoryEntry.from_dict(v) if isinstance(v, dict) else MemoryEntry(value=str(v), hidden=False)
            for k, v in data.items()
        }
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
```

### Step 3: Implement Tokenization and Semantic Search

**File**: `tools/memory/memory.py`

```python
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
```

### Step 4: Implement User Profile Storage Functions

**File**: `tools/memory/memory.py`

```python
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
```

### Step 5: Implement Core Memory API Functions

**File**: `tools/memory/memory.py`

```python
async def remember(
    key: str,
    value: str,
    *,
    category: str = MemoryCategory.USER_PREFERENCE,
    tags: list[str] | None = None,
) -> dict[str, object]:
    """Store a persistent memory."""
    data = _load_raw()
    existing_hidden = data[key].hidden if key in data else False
    existing_count = data[key].access_count if key in data else 0
    created_at = data[key].created_at if key in data else datetime.utcnow()

    data[key] = MemoryEntry(
        value=value,
        hidden=existing_hidden,
        category=category,
        tags=tags or [],
        created_at=created_at,
        updated_at=datetime.utcnow(),
        access_count=existing_count,
    )
    _save_raw(data)
    return {"status": "ok", "key": key, "value": value, "category": category, "tags": tags or []}

async def forget(key: str) -> dict[str, object]:
    """Remove a stored memory by key."""
    data = _load_raw()
    if key not in data:
        return {"status": "not_found", "key": key}
    del data[key]
    _save_raw(data)
    return {"status": "ok", "key": key}

async def search_memory(
    query: str, *,
    category: str | None = None,
    limit: int = 5,
    min_relevance: float = 0.5
) -> dict[str, object]:
    """Search memories using semantic relevance scoring."""
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

    return {"status": "ok", "results": results, "total_found": len(results)}
```

### Step 6: Implement Context-Aware and Profile Functions

**File**: `tools/memory/memory.py`

```python
async def get_relevant_memories(context: str, *, limit: int = 5) -> dict[str, object]:
    """Get memories relevant to the given context."""
    result = await search_memory(context, limit=limit)
    
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
    """Retrieve the structured user profile."""
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
    """Update the user profile with a new preference."""
    profile = _load_profile()
    if "preferences" not in profile:
        profile["preferences"] = {}

    profile["preferences"][preference_key] = {
        "value": value,
        "confidence": confidence,
        "updated_at": datetime.utcnow().isoformat()
    }
    _save_profile(profile)
    return {"status": "ok", "preference_key": preference_key}
```

### Step 7: Implement Memory Consolidation and Statistics

**File**: `tools/memory/memory.py`

```python
async def consolidate_memories(*, dry_run: bool = True) -> dict[str, object]:
    """Find and optionally merge duplicate or similar memories."""
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
    """Get statistics about the memory store."""
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
```

### Step 8: Update Package Exports

**File**: `tools/memory/__init__.py`

```python
"""Persistent key-value memory tools for COMPUTRON with semantic search."""

from .memory import (
    MemoryCategory,
    MemoryEntry,
    consolidate_memories,
    forget,
    get_memory_stats,
    get_relevant_memories,
    get_user_profile,
    load_memory,
    load_user_profile,
    remember,
    save_user_profile,
    search_memory,
    set_key_hidden,
    update_user_profile,
)

__all__ = [
    "MemoryCategory",
    "MemoryEntry",
    "consolidate_memories",
    "forget",
    "get_memory_stats",
    "get_relevant_memories",
    "get_user_profile",
    "load_memory",
    "load_user_profile",
    "remember",
    "save_user_profile",
    "search_memory",
    "set_key_hidden",
    "update_user_profile",
]
```

### Step 9: Integrate with Agent System

**File**: `agents/computron/agent.py`

Update imports:
```python
from tools.memory import (
    forget,
    get_relevant_memories,
    get_user_profile,
    remember,
    search_memory,
    update_user_profile,
)
```

Update SYSTEM_PROMPT to include memory guidance:
```
MEMORY — remember(key, value, category, tags) / forget(key) / search_memory(query).
Enhanced memory system with semantic search, categories, and user profiles:
- Categories: user_preference, project_context, technical_fact, conversation_context,
  skill_preference, personal_info
- Tags: Add descriptive tags for better organization
- Search: Use search_memory(query) to find relevant past memories
- Profile: update_user_profile(key, value) / get_user_profile() for structured preferences

Proactively store:
- User preferences (coding style, communication mode, tools they like)
- Project context (tech stack, architecture patterns, file locations)
- Technical facts (API keys they use, preferred libraries)
- Skill preferences (when to spawn vs load, how they like output formatted)
```

Update TOOLS list:
```python
TOOLS = [
    run_bash_cmd,
    computer_agent_tool,
    browser_agent_tool,
    desktop_agent_tool,
    remember,
    forget,
    search_memory,
    get_relevant_memories,
    get_user_profile,
    update_user_profile,
    goal_planner_tool,
]
```

### Step 10: Create Comprehensive Tests

**File**: `tests/tools/memory/test_memory.py`

Create tests covering:
- Basic memory operations (remember, forget, update)
- Memory metadata (category, tags, timestamps)
- Semantic search (token matching, relevance scoring)
- Category filtering
- Hidden memory exclusion
- Access count tracking
- User profile operations
- Memory consolidation
- Memory statistics
- Edge cases (empty searches, special characters, invalid categories)

See existing test file for complete test patterns.

## Testing Approach

### Unit Tests
Run with: `pytest tests/tools/memory/test_memory.py -v`

### Manual Verification
1. Start computron_9000
2. Store some memories: `remember("python_style", "prefers snake_case", category="user_preference", tags=["python", "coding"])`
3. Search: `search_memory("coding style")` - should return relevant results
4. Update profile: `update_user_profile("editor", "vim", confidence=0.95)`
5. Check stats: `get_memory_stats()`
6. Check consolidation: `consolidate_memories(dry_run=True)`

### Integration Tests
1. Have a conversation where the assistant stores preferences
2. Start a new conversation
3. Ask about the preference - assistant should recall it via memory search

## Dependencies and Prerequisites

### Python Dependencies (already installed)
- Standard library: `dataclasses`, `datetime`, `json`, `re`, `tempfile`, `pathlib`
- Project: `config` module for `load_config()`

### Prerequisites
1. Config system must provide `home_dir` via `load_config().settings.home_dir`
2. Storage directory must be writable
3. Agent system must support async tool functions

## File Summary

### Files to Create
- `tests/tools/memory/__init__.py`

### Files to Modify
1. `tools/memory/memory.py` - Complete rewrite with semantic memory (420 lines)
2. `tools/memory/__init__.py` - Updated exports
3. `agents/computron/agent.py` - Updated imports, system prompt, and TOOLS

### Test Coverage
- 24 comprehensive unit tests covering all functionality
- Tests for edge cases and error conditions
- Mock-based tests for isolated execution

## Backward Compatibility

- Existing `remember(key, value)` calls continue to work
- Default category is `user_preference` for new memories
- Existing memory.json automatically migrated on first write (old format → new format)
- Hidden memory behavior unchanged

## Future Enhancements

Potential improvements for future PRs:
1. **Vector embeddings** - Use sentence transformers for more sophisticated semantic similarity
2. **Memory expiration/TTL** - Automatic cleanup of transient information
3. **Automatic consolidation** - Run consolidation during idle periods
4. **Cross-session summaries** - Conversation continuity across sessions
5. **Profile-driven personalization** - Adapt system prompt based on user profile
6. **Episodic memory integration** - Connect with past conversation summaries
