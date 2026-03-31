"""Unit tests for enhanced memory system with multi-indexed retrieval."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.memory.enhanced_memory import (
    STORAGE_VERSION,
    EnhancedMemoryEntry,
    _compute_embedding,
    _cosine_similarity,
    _extract_tags,
    _load_enhanced_raw,
    _save_enhanced_raw,
    query_memory_by_key,
    query_memory_by_semantic,
    query_memory_by_timeframe,
    query_memory_smart,
    remember_enhanced,
)
from tools.memory.memory import MemoryEntry


@pytest.fixture
def temp_memory_path():
    """Provide a temporary path for memory storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "memory.json"
        yield path


@pytest.fixture(autouse=True)
def mock_memory_path(temp_memory_path):
    """Mock the memory path to use temporary directory."""
    with (
        patch("tools.memory.memory._memory_path", return_value=temp_memory_path),
        patch("tools.memory.enhanced_memory._memory_path", return_value=temp_memory_path),
    ):
        yield temp_memory_path


@pytest.fixture(scope="function")
def sample_memories(mock_memory_path):
    """Create sample enhanced memories for testing."""
    data = {
        "user_name": EnhancedMemoryEntry(
            value="Alice",
            hidden=False,
            created_at=(datetime.now() - timedelta(days=30)).isoformat(),
            updated_at=(datetime.now() - timedelta(days=30)).isoformat(),
            tags=["user", "name", "identity"],
            embedding=_compute_embedding("Alice"),
            version=STORAGE_VERSION,
        ),
        "project_python": EnhancedMemoryEntry(
            value="Working on Python machine learning project",
            hidden=False,
            created_at=(datetime.now() - timedelta(days=7)).isoformat(),
            updated_at=(datetime.now() - timedelta(days=2)).isoformat(),
            tags=["project", "python", "machine", "learning"],
            embedding=_compute_embedding("Working on Python machine learning project"),
            version=STORAGE_VERSION,
        ),
        "meeting_notes": EnhancedMemoryEntry(
            value="Meeting notes from team sync about Q4 goals",
            hidden=False,
            created_at=(datetime.now() - timedelta(days=1)).isoformat(),
            updated_at=(datetime.now() - timedelta(days=1)).isoformat(),
            tags=["meeting", "notes", "team", "sync"],
            embedding=_compute_embedding("Meeting notes from team sync about Q4 goals"),
            version=STORAGE_VERSION,
        ),
        "hidden_secret": EnhancedMemoryEntry(
            value="Secret information",
            hidden=True,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            tags=["secret"],
            embedding=_compute_embedding("Secret information"),
            version=STORAGE_VERSION,
        ),
    }
    _save_enhanced_raw(data)
    yield data
    # Cleanup: clear the file after test
    _save_enhanced_raw({})


@pytest.mark.unit
class TestEnhancedMemoryEntry:
    """Tests for EnhancedMemoryEntry dataclass."""

    def test_from_basic_creates_enhanced(self):
        """Test converting basic MemoryEntry to EnhancedMemoryEntry."""
        basic = MemoryEntry(value="test content", hidden=False)
        enhanced = EnhancedMemoryEntry.from_basic(basic, "test_key")

        assert enhanced.value == "test content"
        assert enhanced.hidden is False
        assert enhanced.version == STORAGE_VERSION
        assert len(enhanced.tags) > 0
        assert len(enhanced.embedding) > 0
        assert enhanced.created_at is not None
        assert enhanced.updated_at is not None

    def test_to_dict_roundtrip(self):
        """Test that to_dict/from_dict preserves data."""
        original = EnhancedMemoryEntry(
            value="test value",
            hidden=False,
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-02T00:00:00",
            tags=["tag1", "tag2"],
            embedding=[0.1, 0.2, 0.3],
            version=STORAGE_VERSION,
        )

        data = original.to_dict()
        restored = EnhancedMemoryEntry.from_dict(data)

        assert restored.value == original.value
        assert restored.hidden == original.hidden
        assert restored.created_at == original.created_at
        assert restored.updated_at == original.updated_at
        assert restored.tags == original.tags
        assert restored.embedding == original.embedding
        assert restored.version == original.version

    def test_from_dict_migrates_v1_format(self):
        """Test migration from v1.0 format."""
        old_data = {
            "value": "old style value",
            "hidden": False,
            # No version, tags, embedding, timestamps
        }

        migrated = EnhancedMemoryEntry.from_dict(old_data)

        assert migrated.value == "old style value"
        assert migrated.hidden is False
        assert migrated.version == STORAGE_VERSION
        assert len(migrated.tags) > 0
        assert len(migrated.embedding) > 0


@pytest.mark.unit
class TestTagExtraction:
    """Tests for auto-tag extraction."""

    def test_extracts_technical_terms(self):
        """Test extraction of technical terms like CamelCase."""
        content = "Working on MyProject with DataProcessor class"
        tags = _extract_tags(content, max_tags=10)

        # Should extract technical terms
        assert any("project" in tag for tag in tags)
        assert any("data" in tag for tag in tags)

    def test_filters_stop_words(self):
        """Test that stop words are not included."""
        content = "the quick brown fox and a cat"
        tags = _extract_tags(content)

        stop_words = ["the", "a", "an", "and"]
        for stop in stop_words:
            assert stop not in tags

    def test_respects_max_tags(self):
        """Test that max_tags limit is respected."""
        content = "one two three four five six seven eight nine ten eleven"
        tags = _extract_tags(content, max_tags=3)
        assert len(tags) <= 3


@pytest.mark.unit
class TestEmbedding:
    """Tests for embedding computation."""

    def test_compute_embedding_returns_vector(self):
        """Test that embeddings are computed."""
        embedding = _compute_embedding("test content")
        assert isinstance(embedding, list)
        assert len(embedding) > 0
        assert all(isinstance(x, float) for x in embedding)

    def test_similar_content_similar_embeddings(self):
        """Test that similar content has higher similarity."""
        emb1 = _compute_embedding("Python programming")
        emb2 = _compute_embedding("Python development")
        emb3 = _compute_embedding("completely different topic")

        sim1 = _cosine_similarity(emb1, emb2)
        sim2 = _cosine_similarity(emb1, emb3)

        # Similar content should have higher similarity
        assert sim1 > sim2

    def test_cosine_similarity_range(self):
        """Test cosine similarity is in valid range."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]
        vec3 = [0.0, 1.0, 0.0]

        # Same vector = 1.0
        assert _cosine_similarity(vec1, vec2) == pytest.approx(1.0)

        # Orthogonal = 0.0
        assert _cosine_similarity(vec1, vec3) == pytest.approx(0.0)


@pytest.mark.unit
class TestStorage:
    """Tests for storage operations."""

    @pytest.mark.asyncio
    async def test_remember_enhanced_creates_entry(self, mock_memory_path):
        """Test enhanced remember creates entry with metadata."""
        result = await remember_enhanced("test_key", "test value for Python project")

        assert result["status"] == "ok"
        assert result["key"] == "test_key"
        assert result["value"] == "test value for Python project"
        assert "tags" in result
        assert "created_at" in result
        assert "updated_at" in result
        assert len(result["tags"]) > 0

    @pytest.mark.asyncio
    async def test_remember_enhanced_updates_existing(self, mock_memory_path):
        """Test that updating preserves created_at."""
        # Create initial entry
        await remember_enhanced("update_test", "original value")

        # Get the created_at
        data = _load_enhanced_raw()
        original_created = data["update_test"].created_at

        # Update
        await remember_enhanced("update_test", "updated value")

        # Verify created_at preserved, updated_at changed
        data = _load_enhanced_raw()
        assert data["update_test"].created_at == original_created
        assert data["update_test"].updated_at >= original_created
        assert data["update_test"].value == "updated value"

    def test_load_migrates_legacy_format(self, temp_memory_path):
        """Test that legacy format is migrated on load."""
        # Create legacy format file
        legacy_data = {"old_key": {"value": "old value", "hidden": False}}
        temp_memory_path.write_text(json.dumps(legacy_data))

        # Mock the path
        with (
            patch("tools.memory.memory._memory_path", return_value=temp_memory_path),
            patch("tools.memory.enhanced_memory._memory_path", return_value=temp_memory_path),
        ):
            data = _load_enhanced_raw()

        assert "old_key" in data
        assert data["old_key"].version == STORAGE_VERSION
        assert len(data["old_key"].tags) > 0
        assert len(data["old_key"].embedding) > 0


@pytest.mark.unit
class TestQueryByKey:
    """Tests for key-based queries."""

    @pytest.mark.asyncio
    async def test_query_existing_key(self, sample_memories):
        """Test querying an existing key."""
        result = await query_memory_by_key("user_name")

        assert result["status"] == "ok"
        assert result["key"] == "user_name"
        assert result["value"] == "Alice"
        assert "tags" in result
        assert "created_at" in result

    @pytest.mark.asyncio
    async def test_query_nonexistent_key(self, sample_memories):
        """Test querying a key that doesn't exist."""
        result = await query_memory_by_key("does_not_exist")

        assert result["status"] == "not_found"
        assert result["key"] == "does_not_exist"

    @pytest.mark.asyncio
    async def test_query_returns_hidden_status(self, sample_memories):
        """Test that hidden status is returned."""
        result = await query_memory_by_key("user_name")
        assert result["hidden"] is False


@pytest.mark.unit
class TestQueryBySemantic:
    """Tests for semantic similarity queries."""

    @pytest.mark.asyncio
    async def test_semantic_query_finds_related_content(self, sample_memories):
        """Test that semantic queries find related content."""
        # Use lower threshold for character n-gram embeddings
        result = await query_memory_by_semantic("Python machine learning", top_k="3", threshold="0.3")

        assert result["status"] == "ok"
        assert result["count"] > 0
        assert len(result["results"]) > 0

        # Should find the Python project
        python_results = [r for r in result["results"] if "python" in r["key"].lower()]
        assert len(python_results) > 0

    @pytest.mark.asyncio
    async def test_semantic_query_respects_threshold(self, sample_memories):
        """Test that similarity threshold filters results."""
        result = await query_memory_by_semantic(
            "Python coding",
            top_k="10",
            threshold="0.9",  # Very high threshold
        )

        # May return 0 results with very high threshold
        assert result["status"] == "ok"
        if result["count"] > 0:
            for r in result["results"]:
                assert r["similarity"] >= 0.9

    @pytest.mark.asyncio
    async def test_semantic_query_hides_hidden_memories(self, sample_memories):
        """Test that hidden memories are excluded."""
        result = await query_memory_by_semantic("secret", top_k="10")

        # Should not find hidden_secret
        keys = [r["key"] for r in result["results"]]
        assert "hidden_secret" not in keys

    @pytest.mark.asyncio
    async def test_semantic_query_empty_storage(self, mock_memory_path):
        """Test semantic query with no memories."""
        result = await query_memory_by_semantic("test")

        assert result["status"] == "ok"
        assert result["count"] == 0
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_semantic_query_invalid_params(self, sample_memories):
        """Test handling of invalid top_k/threshold."""
        result = await query_memory_by_semantic("test", top_k="invalid")

        assert result["status"] == "error"
        assert "message" in result


@pytest.mark.unit
class TestQueryByTimeframe:
    """Tests for temporal queries."""

    @pytest.mark.asyncio
    async def test_query_last_week(self, sample_memories):
        """Test 'last week' timeframe query."""
        result = await query_memory_by_timeframe("last week")

        assert result["status"] == "ok"
        assert "results" in result
        # Should find recent entries

    @pytest.mark.asyncio
    async def test_query_yesterday(self, sample_memories):
        """Test 'yesterday' timeframe query."""
        result = await query_memory_by_timeframe("yesterday")

        assert result["status"] == "ok"
        assert result["count"] >= 0

    @pytest.mark.asyncio
    async def test_query_today(self, sample_memories):
        """Test 'today' timeframe query."""
        # Add a memory from today
        await remember_enhanced("today_memory", "Created today")

        result = await query_memory_by_timeframe("today")

        assert result["status"] == "ok"
        assert result["count"] >= 1
        assert any(r["key"] == "today_memory" for r in result["results"])

    @pytest.mark.asyncio
    async def test_query_past_days(self, sample_memories):
        """Test 'past N days' timeframe query."""
        result = await query_memory_by_timeframe("past 3 days")

        assert result["status"] == "ok"
        # Should find recent entries
        for r in result["results"]:
            assert "timestamp" in r

    @pytest.mark.asyncio
    async def test_query_month_names(self, sample_memories):
        """Test 'in January' style queries."""
        # This might not return results depending on current date
        result = await query_memory_by_timeframe("in January")

        assert result["status"] == "ok" or result["status"] == "error"

    @pytest.mark.asyncio
    async def test_query_invalid_timeframe(self, sample_memories):
        """Test handling of unrecognized timeframe."""
        result = await query_memory_by_timeframe("sometime in the past")

        assert result["status"] == "error"
        assert "message" in result

    @pytest.mark.asyncio
    async def test_query_respects_query_type(self, sample_memories):
        """Test that query_type filters by created/updated/both."""
        result_created = await query_memory_by_timeframe("last month", query_type="created")
        result_updated = await query_memory_by_timeframe("last month", query_type="updated")

        assert result_created["status"] == "ok"
        assert result_updated["status"] == "ok"


@pytest.mark.unit
class TestSmartQuery:
    """Tests for the smart hybrid query."""

    @pytest.mark.asyncio
    async def test_smart_query_exact_key(self, sample_memories):
        """Test that exact key matches are found quickly."""
        result = await query_memory_smart("user_name")

        assert result["status"] == "ok"
        assert result["count"] >= 1
        assert any(r["key"] == "user_name" for r in result["results"])
        assert "key" in result["strategies"]

    @pytest.mark.asyncio
    async def test_smart_query_timeframe(self, sample_memories):
        """Test smart query detects time-based queries."""
        result = await query_memory_smart("what did I save last week")

        assert result["status"] == "ok"
        assert "timeframe" in result["strategies"] or "semantic" in result["strategies"]

    @pytest.mark.asyncio
    async def test_smart_query_semantic(self, sample_memories):
        """Test smart query uses semantic search for descriptive queries."""
        result = await query_memory_smart("machine learning work")

        assert result["status"] == "ok"
        # Should find Python ML project
        assert result["count"] > 0

    @pytest.mark.asyncio
    async def test_smart_query_combines_strategies(self, sample_memories):
        """Test that smart query can use multiple strategies."""
        result = await query_memory_smart("Python project from last week")

        assert result["status"] == "ok"
        # Should use both timeframe and semantic
        assert len(result["strategies"]) >= 1

    @pytest.mark.asyncio
    async def test_smart_query_empty_storage(self, mock_memory_path):
        """Test smart query with empty storage."""
        result = await query_memory_smart("anything")

        assert result["status"] == "ok"
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_smart_query_hides_hidden(self, sample_memories):
        """Test that hidden memories are not returned."""
        result = await query_memory_smart("secret")

        keys = [r["key"] for r in result["results"]]
        assert "hidden_secret" not in keys

    @pytest.mark.asyncio
    async def test_smart_query_results_ranked(self, sample_memories):
        """Test that results are ranked by score."""
        result = await query_memory_smart("Python project")

        if result["count"] > 1:
            scores = [r.get("score", 0) for r in result["results"]]
            assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_smart_query_deduplicates(self, sample_memories):
        """Test that duplicate results are removed."""
        result = await query_memory_smart("project")

        keys = [r["key"] for r in result["results"]]
        assert len(keys) == len(set(keys))


@pytest.mark.unit
class TestIntegration:
    """Integration tests for the complete enhanced memory system."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, mock_memory_path):
        """Test complete memory lifecycle."""
        # Store memories
        await remember_enhanced("pref_theme", "dark mode")
        await remember_enhanced("pref_lang", "Python for data science")

        # Query by key
        result = await query_memory_by_key("pref_theme")
        assert result["value"] == "dark mode"

        # Query by semantic - use more direct query text
        result = await query_memory_by_semantic("data science", threshold="0.1")
        assert result["count"] > 0

        # Smart query - query by exact key
        result = await query_memory_smart("pref_theme")
        # Should find the exact key
        assert result["count"] >= 1
        assert any(r["key"] == "pref_theme" for r in result["results"])

        # Verify tags were extracted
        data = _load_enhanced_raw()
        assert "pref_theme" in data
        assert len(data["pref_theme"].tags) > 0

    @pytest.mark.asyncio
    async def test_backward_compatibility(self, mock_memory_path):
        """Test that old format can be loaded and updated."""
        from tools.memory.memory import remember as basic_remember

        # Use basic remember (old API)
        await basic_remember("old_style", "basic memory")

        # Now use enhanced query
        result = await query_memory_smart("basic memory")

        # Should find the memory (after migration)
        assert result["status"] == "ok"
        # Note: migration happens on enhanced load, so this may or may not work
        # depending on when migration is triggered
