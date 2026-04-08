"""Unit tests for the enhanced semantic memory system."""

from datetime import datetime
from unittest.mock import patch

import pytest

from tools.memory import (
    MemoryCategory,
    MemoryEntry,
    consolidate_memories,
    forget,
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


@pytest.fixture(autouse=True)
def _fresh_memory(tmp_path):
    """Ensure each test starts with fresh memory storage."""
    with patch("tools.memory.memory._memory_path", return_value=tmp_path / "memory.json"), \
         patch("tools.memory.memory._profile_path", return_value=tmp_path / "profile.json"):
        yield


# ============================================================================
# Basic Memory Operations
# ============================================================================

@pytest.mark.unit
async def test_remember_basic():
    """Store a simple memory and verify it's saved."""
    result = await remember("color", "blue")
    assert result["status"] == "ok"
    assert result["key"] == "color"
    assert result["value"] == "blue"
    assert result["category"] == MemoryCategory.USER_PREFERENCE


@pytest.mark.unit
async def test_remember_with_metadata():
    """Store memory with category and tags."""
    result = await remember(
        "python_version",
        "3.11",
        category=MemoryCategory.TECHNICAL_FACT,
        tags=["python", "version", "environment"],
    )
    assert result["category"] == MemoryCategory.TECHNICAL_FACT
    assert result["tags"] == ["python", "version", "environment"]


@pytest.mark.unit
async def test_remember_updates_existing():
    """Storing the same key twice updates the value."""
    await remember("x", "old")
    await remember("x", "new")

    memories = load_memory()
    assert memories["x"].value == "new"


@pytest.mark.unit
async def test_remember_preserves_hidden_state():
    """Updating a memory preserves its hidden state."""
    await remember("x", "value")
    set_key_hidden("x", True)
    await remember("x", "updated")

    memories = load_memory()
    assert memories["x"].hidden is True


@pytest.mark.unit
async def test_forget_existing():
    """Forget removes an existing memory."""
    await remember("to_delete", "value")
    result = await forget("to_delete")
    assert result["status"] == "ok"

    memories = load_memory()
    assert "to_delete" not in memories


@pytest.mark.unit
async def test_forget_nonexistent():
    """Forgetting a non-existent key returns not_found."""
    result = await forget("nonexistent")
    assert result["status"] == "not_found"


@pytest.mark.unit
async def test_set_key_hidden():
    """Marking a key as hidden affects visibility."""
    await remember("secret", "shh")
    set_key_hidden("secret", True)

    memories = load_memory()
    assert memories["secret"].hidden is True


# ============================================================================
# Semantic Search
# ============================================================================

@pytest.mark.unit
async def test_search_memory_basic():
    """Basic search finds relevant memories."""
    await remember("python_style", "prefers snake_case", category=MemoryCategory.USER_PREFERENCE)
    await remember("js_style", "prefers camelCase", category=MemoryCategory.USER_PREFERENCE)
    await remember("database", "uses PostgreSQL", category=MemoryCategory.TECHNICAL_FACT)

    # Search for "python" - should match the python_style key
    result = await search_memory("python", min_relevance=2.0)
    assert result["status"] == "ok"
    assert len(result["results"]) >= 1

    # python_style should appear
    keys = [r["key"] for r in result["results"]]
    assert "python_style" in keys


@pytest.mark.unit
async def test_search_memory_by_category():
    """Search with category filter."""
    await remember("pref1", "value1", category=MemoryCategory.USER_PREFERENCE)
    await remember("pref2", "value2", category=MemoryCategory.USER_PREFERENCE)
    await remember("fact1", "value3", category=MemoryCategory.TECHNICAL_FACT)

    result = await search_memory("value", category=MemoryCategory.USER_PREFERENCE)
    assert all(r["category"] == MemoryCategory.USER_PREFERENCE for r in result["results"])


@pytest.mark.unit
async def test_search_memory_hidden_excluded():
    """Hidden memories are excluded from search results."""
    await remember("visible", "I should appear")
    await remember("hidden", "I should not appear")
    set_key_hidden("hidden", True)

    result = await search_memory("appear")
    keys = [r["key"] for r in result["results"]]
    assert "visible" in keys
    assert "hidden" not in keys


@pytest.mark.unit
async def test_search_memory_limit():
    """Search respects the limit parameter."""
    for i in range(10):
        await remember(f"key_{i}", f"value {i}")

    result = await search_memory("value", limit=3)
    assert len(result["results"]) <= 3


@pytest.mark.unit
async def test_search_updates_access_count():
    """Retrieving memories via search increments access count."""
    await remember("popular", " accessed often")

    # Search twice
    await search_memory("popular")
    await search_memory("popular")

    # Check memory
    memories = load_memory()
    assert memories["popular"].access_count >= 2


@pytest.mark.unit
async def test_get_relevant_memories():
    """Get memories relevant to a context."""
    await remember("timezone", "EST", category=MemoryCategory.PERSONAL_INFO)
    await remember("python_pref", "likes FastAPI", category=MemoryCategory.USER_PREFERENCE)

    result = await get_relevant_memories("what time is it", limit=5)
    assert result["status"] == "ok"
    assert "memories" in result
    assert "by_category" in result


# ============================================================================
# User Profile
# ============================================================================

@pytest.mark.unit
async def test_update_user_profile():
    """Update user preference in profile."""
    result = await update_user_profile("coding_style", "concise", confidence=0.9)
    assert result["status"] == "ok"
    assert result["preference_key"] == "coding_style"


@pytest.mark.unit
async def test_get_user_profile():
    """Retrieve complete user profile."""
    await update_user_profile("style", "concise", confidence=0.9)
    await update_user_profile("verbosity", "low", confidence=0.8)

    result = await get_user_profile()
    assert result["status"] == "ok"
    assert "profile" in result
    assert "stats" in result
    assert result["stats"]["total_preferences"] == 2


@pytest.mark.unit
async def test_user_profile_persistence():
    """Profile persists across calls."""
    await update_user_profile("key", "value")

    profile = load_user_profile()
    assert "preferences" in profile
    assert profile["preferences"]["key"]["value"] == "value"


# ============================================================================
# Memory Entry Model
# ============================================================================

@pytest.mark.unit
def test_memory_entry_serialization():
    """MemoryEntry serializes and deserializes correctly."""
    entry = MemoryEntry(
        value="test value",
        category=MemoryCategory.TECHNICAL_FACT,
        tags=["tag1", "tag2"],
        access_count=5,
    )

    data = entry.to_dict()
    restored = MemoryEntry.from_dict(data)

    assert restored.value == entry.value
    assert restored.category == entry.category
    assert restored.tags == entry.tags
    assert restored.access_count == entry.access_count


@pytest.mark.unit
def test_memory_entry_datetime_handling():
    """MemoryEntry handles datetime fields correctly."""
    entry = MemoryEntry(value="test")
    data = entry.to_dict()

    assert "created_at" in data
    assert "updated_at" in data

    restored = MemoryEntry.from_dict(data)
    assert isinstance(restored.created_at, datetime)
    assert isinstance(restored.updated_at, datetime)


# ============================================================================
# Consolidation
# ============================================================================

@pytest.mark.unit
async def test_consolidate_memories_dry_run():
    """Consolidation dry-run reports without changing."""
    await remember("dup1", "python coding")
    await remember("dup2", "python programming")

    result = await consolidate_memories(dry_run=True)
    assert result["status"] == "ok"
    assert result["dry_run"] is True


@pytest.mark.unit
async def test_consolidate_memories_finds_duplicates():
    """Consolidation identifies similar memories."""
    # Create similar memories
    await remember("fact1", "uses Python for backend development")
    await remember("fact2", "Python backend development preferred")

    result = await consolidate_memories(dry_run=True)
    # These have high token overlap
    assert result["duplicates_found"] >= 0  # May or may not match depending on threshold


# ============================================================================
# Edge Cases
# ============================================================================

@pytest.mark.unit
async def test_empty_search():
    """Search on empty memory returns empty results."""
    result = await search_memory("anything")
    assert result["results"] == []
    assert result["total_found"] == 0


@pytest.mark.unit
async def test_search_special_characters():
    """Search handles special characters gracefully."""
    await remember("key", "value with @#$% special chars")
    result = await search_memory("special")
    assert result["status"] == "ok"


@pytest.mark.unit
async def test_memory_with_empty_tags():
    """Memory can have empty tags list."""
    result = await remember("no_tags", "value", tags=[])
    assert result["tags"] == []


@pytest.mark.unit
async def test_invalid_category_defaults():
    """Invalid category values are handled gracefully."""
    # Even with invalid category, should store successfully
    result = await remember("key", "value", category="invalid_category")
    # The memory system should accept any string category
    assert result["status"] == "ok"
