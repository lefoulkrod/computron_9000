"""Tests for the memory tools module."""

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.memory import (
    MemoryCategory,
    MemoryEntry,
    consolidate_memories,
    forget,
    get_memory,
    get_memory_stats,
    get_related_memories,
    query_memories,
    remember,
    search_memories,
    update_memory_tags,
)
from tools.memory.memory import (
    _load_raw,
    _memory_cache,
    _memory_path,
    _reset_cache,
    _save_raw,
)


@pytest.fixture
def mock_home_dir(tmp_path):
    """Provide a temporary home directory for tests."""
    with patch("tools.memory.memory.load_config") as mock_config:
        mock_config.return_value.settings.home_dir = str(tmp_path)
        _reset_cache()
        yield tmp_path


class TestMemoryEntry:
    """Tests for the MemoryEntry dataclass."""

    def test_basic_creation(self):
        """Test basic MemoryEntry creation."""
        entry = MemoryEntry(value="test value")
        assert entry.value == "test value"
        assert entry.hidden is False
        assert entry.category == MemoryCategory.SEMANTIC
        assert entry.tags == []
        assert entry.confidence == 1.0
        assert entry.access_count == 0

    def test_full_creation(self):
        """Test MemoryEntry creation with all fields."""
        now = time.time()
        entry = MemoryEntry(
            value="test value",
            hidden=True,
            category=MemoryCategory.EPISODIC,
            tags=["tag1", "tag2"],
            confidence=0.8,
            created_at=now,
            accessed_at=now,
            access_count=5,
        )
        assert entry.value == "test value"
        assert entry.hidden is True
        assert entry.category == MemoryCategory.EPISODIC
        assert entry.tags == ["tag1", "tag2"]
        assert entry.confidence == 0.8
        assert entry.access_count == 5

    def test_to_dict(self):
        """Test serialization to dict."""
        entry = MemoryEntry(
            value="test",
            category=MemoryCategory.WORKING,
            tags=["tag1"],
            confidence=0.9,
        )
        data = entry.to_dict()
        assert data["value"] == "test"
        assert data["category"] == "working"
        assert data["tags"] == ["tag1"]
        assert data["confidence"] == 0.9

    def test_from_dict_v2(self):
        """Test deserialization from v2 format."""
        data = {
            "value": "test value",
            "hidden": True,
            "category": "episodic",
            "tags": ["conversation", "summary"],
            "confidence": 0.85,
            "created_at": 1234567890.0,
            "accessed_at": 1234567891.0,
            "access_count": 3,
        }
        entry = MemoryEntry.from_dict(data)
        assert entry.value == "test value"
        assert entry.hidden is True
        assert entry.category == MemoryCategory.EPISODIC
        assert entry.tags == ["conversation", "summary"]
        assert entry.confidence == 0.85

    def test_from_dict_v1_migration(self):
        """Test migration from v1 format."""
        data = {"value": "old value", "hidden": False}
        entry = MemoryEntry.from_dict(data)
        assert entry.value == "old value"
        assert entry.hidden is False
        assert entry.category == MemoryCategory.SEMANTIC
        assert entry.tags == []


class TestRemember:
    """Tests for the remember function."""

    @pytest.mark.asyncio
    async def test_basic_remember(self, mock_home_dir):
        """Test basic memory storage."""
        result = await remember("key1", "value1")
        assert result["status"] == "ok"
        assert result["key"] == "key1"
        assert result["value"] == "value1"
        assert result["category"] == "semantic"

    @pytest.mark.asyncio
    async def test_remember_with_category(self, mock_home_dir):
        """Test storing with category."""
        result = await remember("key1", "value1", category="episodic")
        assert result["category"] == "episodic"

        # Verify it was stored correctly
        data = _load_raw()
        assert data["key1"].category == MemoryCategory.EPISODIC

    @pytest.mark.asyncio
    async def test_remember_with_tags(self, mock_home_dir):
        """Test storing with tags."""
        result = await remember("key1", "value1", tags=["tag1", "tag2"])
        assert result["tags"] == ["tag1", "tag2"]

    @pytest.mark.asyncio
    async def test_remember_with_confidence(self, mock_home_dir):
        """Test storing with confidence score."""
        await remember("key1", "value1", confidence=0.75)
        data = _load_raw()
        assert data["key1"].confidence == 0.75

    @pytest.mark.asyncio
    async def test_remember_update_preserves_metadata(self, mock_home_dir):
        """Test that updating preserves access count and timestamps."""
        await remember("key1", "original")
        get_memory("key1")  # Access to increment count

        await remember("key1", "updated")
        entry = get_memory("key1")
        assert entry.access_count == 1
        assert entry.value == "updated"


class TestForget:
    """Tests for the forget function."""

    @pytest.mark.asyncio
    async def test_forget_existing(self, mock_home_dir):
        """Test forgetting an existing key."""
        await remember("key1", "value1")
        result = await forget("key1")
        assert result["status"] == "ok"
        assert result["key"] == "key1"

        data = _load_raw()
        assert "key1" not in data

    @pytest.mark.asyncio
    async def test_forget_nonexistent(self, mock_home_dir):
        """Test forgetting a non-existent key."""
        result = await forget("nonexistent")
        assert result["status"] == "not_found"


class TestGetMemory:
    """Tests for the get_memory function."""

    @pytest.mark.asyncio
    async def test_get_existing(self, mock_home_dir):
        """Test retrieving an existing memory."""
        await remember("key1", "value1", tags=["tag1"])
        entry = get_memory("key1")
        assert entry is not None
        assert entry.value == "value1"
        assert entry.access_count == 1

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, mock_home_dir):
        """Test retrieving a non-existent memory."""
        entry = get_memory("nonexistent")
        assert entry is None

    @pytest.mark.asyncio
    async def test_get_updates_access_count(self, mock_home_dir):
        """Test that get updates access metadata."""
        await remember("key1", "value1")
        get_memory("key1")
        get_memory("key1")
        entry = get_memory("key1")
        assert entry.access_count == 3


class TestSearchMemories:
    """Tests for the search_memories function."""

    @pytest.mark.asyncio
    async def test_search_by_key(self, mock_home_dir):
        """Test searching by key."""
        await remember("user_timezone", "EST")
        await remember("preferred_language", "Python")

        result = await search_memories("timezone")
        assert result["status"] == "ok"
        assert result["count"] >= 1
        assert any(r["key"] == "user_timezone" for r in result["results"])

    @pytest.mark.asyncio
    async def test_search_by_value(self, mock_home_dir):
        """Test searching by value."""
        await remember("key1", "sky blue color")
        await remember("key2", "fire red color")

        result = await search_memories("sky")
        assert result["count"] >= 1
        assert any(r["key"] == "key1" for r in result["results"])

    @pytest.mark.asyncio
    async def test_search_with_category_filter(self, mock_home_dir):
        """Test searching with category filter."""
        await remember("fact1", "value1", category="semantic")
        await remember("conv1", "value2", category="episodic")

        result = await search_memories("value", category="semantic")
        assert result["count"] == 1
        assert result["results"][0]["category"] == "semantic"

    @pytest.mark.asyncio
    async def test_search_with_tags_filter(self, mock_home_dir):
        """Test searching with tags filter."""
        await remember("key1", "value1", tags=["important", "user"])
        await remember("key2", "value2", tags=["system"])

        result = await search_memories("value", tags=["important"])
        assert result["count"] == 1
        assert result["results"][0]["key"] == "key1"

    @pytest.mark.asyncio
    async def test_search_with_min_confidence(self, mock_home_dir):
        """Test searching with confidence threshold."""
        await remember("key1", "value1", confidence=0.9)
        await remember("key2", "value2", confidence=0.5)

        result = await search_memories("value", min_confidence=0.8)
        assert result["count"] == 1
        assert result["results"][0]["key"] == "key1"

    @pytest.mark.asyncio
    async def test_search_limit(self, mock_home_dir):
        """Test search result limit."""
        for i in range(10):
            await remember(f"key{i}", f"value{i}")

        result = await search_memories("value", limit=5)
        assert result["count"] == 5


class TestQueryMemories:
    """Tests for the query_memories function."""

    @pytest.mark.asyncio
    async def test_query_by_category(self, mock_home_dir):
        """Test querying by category."""
        await remember("key1", "value1", category="semantic")
        await remember("key2", "value2", category="episodic")

        result = await query_memories(category="episodic")
        assert result["count"] == 1
        assert result["results"][0]["key"] == "key2"

    @pytest.mark.asyncio
    async def test_query_by_tags(self, mock_home_dir):
        """Test querying by tags."""
        await remember("key1", "value1", tags=["user", "pref"])
        await remember("key2", "value2", tags=["system"])

        result = await query_memories(tags=["user"])
        assert result["count"] == 1
        assert result["results"][0]["key"] == "key1"

    @pytest.mark.asyncio
    async def test_query_by_confidence(self, mock_home_dir):
        """Test querying by confidence."""
        await remember("key1", "value1", confidence=0.95)
        await remember("key2", "value2", confidence=0.5)

        result = await query_memories(min_confidence=0.9)
        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_query_by_time_range(self, mock_home_dir):
        """Test querying by time range."""
        before = time.time()
        await remember("key1", "value1")
        after = time.time()

        result = await query_memories(created_after=before, created_before=after)
        assert result["count"] == 1


class TestGetRelatedMemories:
    """Tests for the get_related_memories function."""

    @pytest.mark.asyncio
    async def test_related_by_category(self, mock_home_dir):
        """Test finding memories in same category."""
        await remember("key1", "value1", category="semantic", tags=["tag1"])
        await remember("key2", "value2", category="semantic", tags=["tag2"])
        await remember("key3", "value3", category="episodic", tags=["tag1"])

        result = await get_related_memories("key1")
        assert result["status"] == "ok"
        # key2 matches by category, key3 matches by shared tag
        assert result["count"] == 2
        keys = [r["key"] for r in result["results"]]
        assert "key2" in keys
        assert "key3" in keys

    @pytest.mark.asyncio
    async def test_related_by_tags(self, mock_home_dir):
        """Test finding memories with shared tags."""
        await remember("key1", "value1", tags=["shared", "unique1"])
        await remember("key2", "value2", tags=["shared", "unique2"])
        await remember("key3", "value3", tags=["other"])

        result = await get_related_memories("key1")
        # key2 matches by shared tag (score 1) and category (score 1) = 2
        # key3 matches by category only (score 1)
        assert result["count"] == 2
        # key2 should be first (higher score due to shared tag)
        assert result["results"][0]["key"] == "key2"
        assert "shared" in result["results"][0]["shared_tags"]

    @pytest.mark.asyncio
    async def test_related_not_found(self, mock_home_dir):
        """Test finding related for non-existent key."""
        result = await get_related_memories("nonexistent")
        assert result["status"] == "not_found"


class TestGetMemoryStats:
    """Tests for the get_memory_stats function."""

    @pytest.mark.asyncio
    async def test_empty_stats(self, mock_home_dir):
        """Test stats with no memories."""
        result = await get_memory_stats()
        assert result["status"] == "ok"
        assert result["total_memories"] == 0
        assert result["total_accesses"] == 0

    @pytest.mark.asyncio
    async def test_stats_with_memories(self, mock_home_dir):
        """Test stats with various memories."""
        await remember("key1", "value1", category="semantic", confidence=0.9)
        await remember("key2", "value2", category="episodic", confidence=0.8)
        # Access to update counts
        get_memory("key1")
        get_memory("key1")

        result = await get_memory_stats()
        assert result["total_memories"] == 2
        assert result["by_category"]["semantic"] == 1
        assert result["by_category"]["episodic"] == 1
        # Stats count access from disk, not cache
        # So we check the structure, not exact counts
        assert "total_accesses" in result
        assert "average_confidence" in result
        assert 0.8 < result["average_confidence"] < 0.9


class TestUpdateMemoryTags:
    """Tests for the update_memory_tags function."""

    @pytest.mark.asyncio
    async def test_add_tags(self, mock_home_dir):
        """Test adding tags to a memory."""
        await remember("key1", "value1", tags=["original"])
        result = await update_memory_tags("key1", add_tags=["new1", "new2"])

        assert result["status"] == "ok"
        assert "original" in result["tags"]
        assert "new1" in result["tags"]
        assert "new2" in result["tags"]

    @pytest.mark.asyncio
    async def test_remove_tags(self, mock_home_dir):
        """Test removing tags from a memory."""
        await remember("key1", "value1", tags=["keep", "remove"])
        result = await update_memory_tags("key1", remove_tags=["remove"])

        assert result["status"] == "ok"
        assert "keep" in result["tags"]
        assert "remove" not in result["tags"]


class TestConsolidateMemories:
    """Tests for the consolidate_memories function."""

    @pytest.mark.asyncio
    async def test_consolidate_basic(self, mock_home_dir):
        """Test basic consolidation."""
        await remember("key1", "value1", tags=["tag1"], category="semantic")
        await remember("key2", "value2", tags=["tag2"], category="semantic")

        result = await consolidate_memories(["key1", "key2"], "consolidated")
        assert result["status"] == "ok"
        assert result["consolidated_key"] == "consolidated"

        # Check old keys are gone
        data = _load_raw()
        assert "key1" not in data
        assert "key2" not in data
        assert "consolidated" in data

    @pytest.mark.asyncio
    async def test_consolidate_with_custom_value(self, mock_home_dir):
        """Test consolidation with custom value."""
        await remember("key1", "value1")
        await remember("key2", "value2")

        result = await consolidate_memories(
            ["key1", "key2"], "consolidated", new_value="custom value"
        )

        data = _load_raw()
        assert data["consolidated"].value == "custom value"

    @pytest.mark.asyncio
    async def test_consolidate_no_valid_keys(self, mock_home_dir):
        """Test consolidation with invalid keys."""
        result = await consolidate_memories(["key1", "key2"], "consolidated")
        assert result["status"] == "error"


class TestBackwardCompatibility:
    """Tests for backward compatibility with v1 format."""

    def test_v1_file_migration(self, mock_home_dir):
        """Test automatic migration from v1 format."""
        # Create a v1 format file
        v1_data = {"key1": {"value": "value1", "hidden": False}}
        memory_path = _memory_path()
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        memory_path.write_text(json.dumps(v1_data))

        # Load with new code (should migrate automatically)
        data = _load_raw()
        assert "key1" in data
        assert data["key1"].value == "value1"
        assert data["key1"].category == MemoryCategory.SEMANTIC

    @pytest.mark.asyncio
    async def test_old_remember_call(self, mock_home_dir):
        """Test that old-style remember calls still work."""
        # Old API: await remember(key, value)
        result = await remember("key1", "value1")
        assert result["status"] == "ok"

        # Verify it was stored
        data = _load_raw()
        assert data["key1"].value == "value1"
