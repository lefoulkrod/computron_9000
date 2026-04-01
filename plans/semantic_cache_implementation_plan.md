# Implementation Plan: Intelligent Tool Result Caching with Semantic Matching

## Overview

This plan implements a `@semantic_cached` decorator that caches tool results based on semantic similarity of arguments. Instead of requiring exact hash matches, it uses embeddings to find similar previous queries and returns cached results, dramatically reducing redundant operations for repetitive tasks.

## Key Features

1. **Semantic Cache Lookup**: Uses sentence-transformers embeddings to match similar queries
2. **TTL Support**: Time-based cache expiration
3. **Cache Invalidation**: Automatic invalidation on file changes or explicit invalidation API
4. **Metrics**: Cache hit/miss tracking for observability
5. **Configurable Threshold**: Adjustable similarity threshold for matching
6. **Hybrid Approach**: Combines exact cache lookup with semantic fallback

---

## Phase 1: Core Cache Infrastructure

### 1.1 Create `utils/semantic_cache.py`

**New File**: `/home/computron/computron_9000/utils/semantic_cache.py`

**Purpose**: Core semantic caching utilities using sentence-transformers embeddings.

**Code Structure**:
```python
"""Semantic cache for tool results with embedding-based similarity matching."""

import asyncio
import functools
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ParamSpec, TypeVar, Generic, Callable, Awaitable

import numpy as np
from sentence_transformers import SentenceTransformer
import cachetools

P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger(__name__)

# Global model instance (lazy loaded)
_model: SentenceTransformer | None = None

def _get_model() -> SentenceTransformer:
    """Lazy-load the embedding model."""
    global _model
    if _model is None:
        # Use lightweight model suitable for semantic similarity
        _model = SentenceTransformer('all-MiniLM-L6-v2')
    return _model

def _compute_embedding(text: str) -> np.ndarray:
    """Compute embedding for text."""
    model = _get_model()
    return model.encode(text, convert_to_numpy=True)

def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

@dataclass
class CachedEntry:
    """A cached result with metadata."""
    
    key_hash: str              # Exact key hash for fast lookup
    embedding: np.ndarray      # Semantic embedding
    result: Any               # Cached result
    timestamp: float          # When cached
    ttl: float                # TTL in seconds
    access_count: int = 0     # For LRU tracking
    last_accessed: float = field(default_factory=time.time)
    
    def is_expired(self) -> bool:
        return time.time() - self.timestamp > self.ttl

class SemanticCache:
    """In-memory semantic cache with TTL and LRU eviction."""
    
    def __init__(self, maxsize: int = 1000, default_ttl: float = 300.0, similarity_threshold: float = 0.92):
        self.maxsize = maxsize
        self.default_ttl = default_ttl
        self.similarity_threshold = similarity_threshold
        self._exact_cache: dict[str, CachedEntry] = {}
        self._semantic_entries: list[CachedEntry] = []  # For semantic search
        self._lock = asyncio.Lock()
    
    def _compute_key_hash(self, *args: Any, **kwargs: Any) -> str:
        """Compute hash key for exact matching."""
        key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        return hashlib.sha256(key_data.encode()).hexdigest()
    
    def _compute_embedding(self, *args: Any, **kwargs: Any) -> np.ndarray:
        """Compute embedding for semantic matching."""
        key_text = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        return _compute_embedding(key_text)
    
    async def get(self, *args: Any, **kwargs: Any) -> CachedEntry | None:
        """Get cached entry by exact or semantic match."""
        async with self._lock:
            key_hash = self._compute_key_hash(*args, **kwargs)
            
            # Try exact match first
            if key_hash in self._exact_cache:
                entry = self._exact_cache[key_hash]
                if not entry.is_expired():
                    entry.access_count += 1
                    entry.last_accessed = time.time()
                    return entry
                else:
                    # Remove expired entry
                    del self._exact_cache[key_hash]
                    self._semantic_entries = [e for e in self._semantic_entries if e.key_hash != key_hash]
            
            # Try semantic match
            query_embedding = self._compute_embedding(*args, **kwargs)
            best_match: CachedEntry | None = None
            best_similarity = 0.0
            
            for entry in self._semantic_entries:
                if entry.is_expired():
                    continue
                similarity = _cosine_similarity(query_embedding, entry.embedding)
                if similarity > self.similarity_threshold and similarity > best_similarity:
                    best_similarity = similarity
                    best_match = entry
            
            if best_match:
                best_match.access_count += 1
                best_match.last_accessed = time.time()
                logger.debug("Semantic cache hit with similarity %.3f", best_similarity)
            
            return best_match
    
    async def set(self, result: Any, ttl: float | None = None, *args: Any, **kwargs: Any) -> None:
        """Store result in cache."""
        async with self._lock:
            key_hash = self._compute_key_hash(*args, **kwargs)
            embedding = self._compute_embedding(*args, **kwargs)
            
            entry = CachedEntry(
                key_hash=key_hash,
                embedding=embedding,
                result=result,
                timestamp=time.time(),
                ttl=ttl or self.default_ttl,
            )
            
            self._exact_cache[key_hash] = entry
            self._semantic_entries.append(entry)
            
            # LRU eviction if over size
            if len(self._semantic_entries) > self.maxsize:
                self._semantic_entries.sort(key=lambda e: (e.access_count, e.last_accessed))
                removed = self._semantic_entries.pop(0)
                if removed.key_hash in self._exact_cache:
                    del self._exact_cache[removed.key_hash]
    
    async def clear(self) -> None:
        """Clear all cached entries."""
        async with self._lock:
            self._exact_cache.clear()
            self._semantic_entries.clear()
    
    def get_stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        return {
            "size": len(self._semantic_entries),
            "maxsize": self.maxsize,
            "exact_hits": sum(1 for e in self._semantic_entries if e.access_count > 0),
        }

# Registry of caches per function
_cache_registry: dict[str, SemanticCache] = {}
_metrics_registry: dict[str, dict[str, int]] = {}

def get_cache(func_name: str) -> SemanticCache:
    """Get or create cache for a function."""
    if func_name not in _cache_registry:
        _cache_registry[func_name] = SemanticCache()
        _metrics_registry[func_name] = {"hits": 0, "misses": 0, "semantic_hits": 0}
    return _cache_registry[func_name]

def get_metrics(func_name: str | None = None) -> dict[str, Any]:
    """Get cache metrics for all or specific function."""
    if func_name:
        return _metrics_registry.get(func_name, {})
    return _metrics_registry.copy()

def clear_all_caches() -> None:
    """Clear all semantic caches."""
    for cache in _cache_registry.values():
        asyncio.create_task(cache.clear())
    _metrics_registry.clear()
```

### 1.2 Add Dependencies to `pyproject.toml`

**Modify**: `/home/computron/computron_9000/pyproject.toml`

Add to `[project].dependencies`:
```toml
dependencies = [
    # ... existing deps ...
    "sentence-transformers>=3.0.0",  # For semantic caching
    "numpy>=1.26.0",                 # Required by sentence-transformers
]
```

---

## Phase 2: The `@semantic_cached` Decorator

### 2.1 Extend `utils/semantic_cache.py`

**Add to existing file**:

```python
def semantic_cached(
    ttl: float = 300.0,
    similarity_threshold: float = 0.92,
    maxsize: int = 1000,
    key_func: Callable[..., str] | None = None,
    invalidate_on: list[str] | None = None,
):
    """Decorator for semantic caching of async functions.
    
    Args:
        ttl: Time-to-live in seconds for cached entries
        similarity_threshold: Cosine similarity threshold for semantic matching (0-1)
        maxsize: Maximum number of cached entries
        key_func: Optional function to extract cache key from arguments
        invalidate_on: List of file paths; cache invalidated when files change
    
    Example:
        @semantic_cached(ttl=600, similarity_threshold=0.9)
        async def search_web(query: str) -> dict:
            # This will cache results and return cached for similar queries
            return await fetch_results(query)
    """
    
    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        cache_key = f"{func.__module__}.{func.__qualname__}"
        cache = SemanticCache(maxsize=maxsize, default_ttl=ttl, similarity_threshold=similarity_threshold)
        _cache_registry[cache_key] = cache
        
        if cache_key not in _metrics_registry:
            _metrics_registry[cache_key] = {"hits": 0, "misses": 0, "semantic_hits": 0}
        
        # Track file modification times for invalidation
        file_mtimes: dict[str, float] = {}
        if invalidate_on:
            for path in invalidate_on:
                try:
                    file_mtimes[path] = Path(path).stat().st_mtime
                except OSError:
                    pass
        
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # Check if files changed (invalidate cache)
            if invalidate_on:
                for path in invalidate_on:
                    try:
                        mtime = Path(path).stat().st_mtime
                        if file_mtimes.get(path) != mtime:
                            await cache.clear()
                            file_mtimes[path] = mtime
                            break
                    except OSError:
                        pass
            
            # Check cache
            cached = await cache.get(*args, **kwargs)
            if cached is not None:
                _metrics_registry[cache_key]["hits"] += 1
                return cached.result
            
            # Execute and cache
            _metrics_registry[cache_key]["misses"] += 1
            result = await func(*args, **kwargs)
            await cache.set(result, ttl, *args, **kwargs)
            return result
        
        # Attach cache management methods
        wrapper.cache = cache  # type: ignore[attr-defined]
        wrapper.clear_cache = cache.clear  # type: ignore[attr-defined]
        wrapper.get_stats = cache.get_stats  # type: ignore[attr-defined]
        
        return wrapper
    
    return decorator
```

---

## Phase 3: Apply Caching to Tool Functions

### 3.1 Modify `tools/web/get_webpage.py`

**Modify**: `/home/computron/computron_9000/tools/web/get_webpage.py`

**Changes**:
```python
# Add import at top
from utils.semantic_cache import semantic_cached

# Replace existing cache decorator
@semantic_cached(ttl=3600, similarity_threshold=0.90)  # 1 hour TTL, 90% similarity threshold
async def get_webpage(url: str, max_length: int | None = None) -> ReducedWebpage | GetWebpageError:
    """Fetch and reduce a webpage to plain text with links.
    
    Args:
        url: The URL to fetch.
        max_length: Optional max character limit for the text.
    
    Returns:
        ReducedWebpage containing text and links, or GetWebpageError on failure.
    """
    # existing implementation...
```

### 3.2 Modify `tools/virtual_computer/read_ops.py`

**Modify**: `/home/computron/computron_9000/tools/virtual_computer/read_ops.py`

**Add caching to `read_file`**:

```python
from utils.semantic_cache import semantic_cached

@semantic_cached(
    ttl=60,  # 1 minute TTL for file reads
    similarity_threshold=0.95,  # High threshold - files must be very similar
    invalidate_on=None,  # Cache invalidates on content changes via timestamp
)
def read_file(path: str, start: int | None = None, end: int | None = None) -> ReadTextResult:
    """Read a UTF-8 text file fully or by line range.
    
    Cached based on file path and content hash to avoid re-reading unchanged files.
    ...
    """
    # existing implementation...
```

**Note**: For file operations, we need to add content-based invalidation:

```python
# In semantic_cache.py, add content-aware invalidation option

def _get_file_hash(path: str) -> str:
    """Get hash of file content for change detection."""
    try:
        import hashlib
        with open(path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception:
        return ""
```

### 3.3 Modify `tools/web/search_google.py`

**Modify**: `/home/computron/computron_9000/tools/web/search_google.py`

```python
from utils.semantic_cache import semantic_cached

@semantic_cached(ttl=1800, similarity_threshold=0.85)  # 30 min TTL, 85% similarity
async def search_google(query: str, num_results: int = 10) -> list[SearchResult]:
    """Search Google and return results.
    
    Similar queries ("python tutorial" vs "python tutorials") share cached results.
    """
    # existing implementation...
```

---

## Phase 4: Cache Metrics and Observability

### 4.1 Add Metrics Endpoint

**New File**: `/home/computron/computron_9000/server/cache_metrics.py`

```python
"""Cache metrics endpoint for monitoring."""

from aiohttp import web
from utils.semantic_cache import get_metrics

async def cache_metrics_handler(request: web.Request) -> web.Response:
    """Return cache metrics as JSON."""
    return web.json_response(get_metrics())

async def cache_clear_handler(request: web.Request) -> web.Response:
    """Clear all caches (admin only)."""
    from utils.semantic_cache import clear_all_caches
    clear_all_caches()
    return web.json_response({"status": "cleared"})

def setup_cache_routes(app: web.Application) -> None:
    """Add cache routes to aiohttp app."""
    app.router.add_get("/api/cache/metrics", cache_metrics_handler)
    app.router.add_post("/api/cache/clear", cache_clear_handler)
```

### 4.2 Update `server/aiohttp_app.py`

**Modify**: `/home/computron/computron_9000/server/aiohttp_app.py`

Add near line where other routes are registered:
```python
from server.cache_metrics import setup_cache_routes

# In app setup:
setup_cache_routes(app)
```

---

## Phase 5: Testing

### 5.1 Create `tests/utils/test_semantic_cache.py`

**New File**: `/home/computron/computron_9000/tests/utils/test_semantic_cache.py`

```python
"""Tests for semantic caching utilities."""

import asyncio
import time
from typing import Any

import pytest
import numpy as np

from utils.semantic_cache import (
    SemanticCache,
    semantic_cached,
    get_metrics,
    clear_all_caches,
    _cosine_similarity,
)


class TestSemanticCache:
    """Test the SemanticCache class."""
    
    @pytest.mark.asyncio
    async def test_exact_match_returns_cached(self) -> None:
        """Exact argument match returns cached value."""
        cache = SemanticCache()
        await cache.set("result1", 300, "arg1", kwarg1="val1")
        
        result = await cache.get("arg1", kwarg1="val1")
        assert result is not None
        assert result.result == "result1"
    
    @pytest.mark.asyncio
    async def test_semantic_match_finds_similar(self) -> None:
        """Semantically similar arguments find cached value."""
        cache = SemanticCache(similarity_threshold=0.90)
        await cache.set("result1", 300, "python tutorial for beginners")
        
        # Similar query should match
        result = await cache.get("beginner python tutorial")
        assert result is not None
        assert result.result == "result1"
    
    @pytest.mark.asyncio
    async def test_dissimilar_queries_miss(self) -> None:
        """Dissimilar queries should not match."""
        cache = SemanticCache(similarity_threshold=0.95)
        await cache.set("result1", 300, "machine learning")
        
        # Different topic should not match
        result = await cache.get("cooking recipes")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_ttl_expiration(self) -> None:
        """Cached entries expire after TTL."""
        cache = SemanticCache()
        await cache.set("result1", ttl=0.1, "arg1")  # 100ms TTL
        
        # Should find immediately
        result = await cache.get("arg1")
        assert result is not None
        
        # Wait for expiration
        await asyncio.sleep(0.2)
        
        # Should be expired
        result = await cache.get("arg1")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_lru_eviction(self) -> None:
        """Oldest entries evicted when maxsize reached."""
        cache = SemanticCache(maxsize=2)
        await cache.set("result1", 300, "arg1")
        await cache.set("result2", 300, "arg2")
        await cache.set("result3", 300, "arg3")  # Should evict arg1
        
        assert len(cache._semantic_entries) == 2
        assert "arg1" not in [e for e in cache._semantic_entries]


class TestSemanticCachedDecorator:
    """Test the @semantic_cached decorator."""
    
    @pytest.mark.asyncio
    async def test_decorator_caches_results(self) -> None:
        """Decorator caches function results."""
        calls = 0
        
        @semantic_cached(ttl=300)
        async def test_func(query: str) -> str:
            nonlocal calls
            calls += 1
            return f"result for {query}"
        
        # First call should execute
        result1 = await test_func("test query")
        assert calls == 1
        assert result1 == "result for test query"
        
        # Second call with same args should hit cache
        result2 = await test_func("test query")
        assert calls == 1  # No new execution
        assert result2 == "result for test query"
    
    @pytest.mark.asyncio
    async def test_decorator_semantic_matching(self) -> None:
        """Decorator matches semantically similar queries."""
        calls = 0
        
        @semantic_cached(ttl=300, similarity_threshold=0.90)
        async def search(query: str) -> str:
            nonlocal calls
            calls += 1
            return f"results for {query}"
        
        await search("python programming")
        assert calls == 1
        
        # Similar query should use cache
        result = await search("programming in python")
        assert calls == 1  # Still cached
        assert result == "results for python programming"
    
    @pytest.mark.asyncio
    async def test_decorator_metrics_tracking(self) -> None:
        """Decorator tracks cache metrics."""
        @semantic_cached(ttl=300)
        async def test_func(x: int) -> int:
            return x * 2
        
        await test_func(5)
        await test_func(5)
        await test_func(5)
        
        metrics = get_metrics("test_semantic_cache.test_decorator_metrics_tracking.<locals>.test_func")
        assert metrics["hits"] >= 2
        assert metrics["misses"] >= 1
    
    def test_teardown(self) -> None:
        """Clear caches after each test."""
        clear_all_caches()


class TestCosineSimilarity:
    """Test cosine similarity computation."""
    
    def test_identical_vectors(self) -> None:
        """Identical vectors have similarity 1.0."""
        a = np.array([1.0, 0.0, 0.0])
        assert _cosine_similarity(a, a) == pytest.approx(1.0)
    
    def test_opposite_vectors(self) -> None:
        """Opposite vectors have similarity -1.0."""
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([-1.0, 0.0, 0.0])
        assert _cosine_similarity(a, b) == pytest.approx(-1.0)
    
    def test_orthogonal_vectors(self) -> None:
        """Orthogonal vectors have similarity 0.0."""
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert _cosine_similarity(a, b) == pytest.approx(0.0)


class TestCacheStats:
    """Test cache statistics."""
    
    @pytest.mark.asyncio
    async def test_stats_reporting(self) -> None:
        """Cache reports accurate statistics."""
        cache = SemanticCache(maxsize=100)
        await cache.set("r1", 300, "a1")
        await cache.set("r2", 300, "a2")
        
        stats = cache.get_stats()
        assert stats["size"] == 2
        assert stats["maxsize"] == 100
```

### 5.2 Create `tests/tools/test_cached_tools.py`

**New File**: `/home/computron/computron_9000/tests/tools/test_cached_tools.py`

```python
"""Integration tests for cached tool functions."""

import pytest
from unittest.mock import patch, MagicMock

from utils.semantic_cache import clear_all_caches


class TestCachedWebTools:
    """Test that web tools properly cache results."""
    
    @pytest.fixture(autouse=True)
    def clear_caches(self) -> None:
        """Clear all caches before each test."""
        clear_all_caches()
    
    @pytest.mark.asyncio
    async def test_get_webpage_caches(self) -> None:
        """get_webpage caches and returns cached for similar URLs."""
        from tools.web.get_webpage import get_webpage
        
        # Mock the underlying fetch
        with patch('tools.web.get_webpage._get_webpage_raw') as mock_fetch:
            mock_fetch.return_value = "<html><body>Test content</body></html>"
            
            # First call
            result1 = await get_webpage("https://example.com/page1")
            assert mock_fetch.call_count == 1
            
            # Same URL should use cache
            result2 = await get_webpage("https://example.com/page1")
            assert mock_fetch.call_count == 1  # No new fetch
            assert result1.page_text == result2.page_text


class TestCachedFileTools:
    """Test that file tools properly cache results."""
    
    @pytest.fixture(autouse=True)
    def clear_caches(self) -> None:
        """Clear all caches before each test."""
        clear_all_caches()
    
    def test_read_file_caches_unchanged_files(self) -> None:
        """read_file caches unchanged file content."""
        from tools.virtual_computer.read_ops import read_file
        
        # This would need a real file or mocking
        # Implementation depends on test setup
        pass
```

---

## Phase 6: Configuration

### 6.1 Update `config.yaml`

**Add section** to `/home/computron/computron_9000/config.yaml`:

```yaml
semantic_cache:
  enabled: true
  default_ttl: 300  # 5 minutes
  default_similarity_threshold: 0.92
  maxsize_per_function: 1000
  metrics_enabled: true
  
  # Per-function overrides
  tools:
    get_webpage:
      ttl: 3600  # 1 hour
      similarity_threshold: 0.90
    read_file:
      ttl: 60  # 1 minute
      similarity_threshold: 0.95
    search_google:
      ttl: 1800  # 30 minutes
      similarity_threshold: 0.85
```

### 6.2 Update `config.py` (if exists) or create config loader

**Create/Modify** to load semantic cache config and make it available globally.

---

## Phase 7: Documentation

### 7.1 Create `docs/SEMANTIC_CACHE.md`

**New File**: `/home/computron/computron_9000/docs/SEMANTIC_CACHE.md`

```markdown
# Semantic Cache Documentation

## Overview

The semantic cache system provides intelligent caching for tool results based on semantic similarity rather than exact string matching. This allows queries like "python tutorial" and "tutorials for python" to share cached results.

## How It Works

1. **Embedding Generation**: Each query is converted to a vector embedding using `all-MiniLM-L6-v2`
2. **Exact Match First**: The system first checks for exact hash matches
3. **Semantic Fallback**: If no exact match, it compares embeddings using cosine similarity
4. **Threshold Filtering**: Only matches above `similarity_threshold` are returned

## Configuration

### Global Settings (config.yaml)

```yaml
semantic_cache:
  enabled: true
  default_ttl: 300
  default_similarity_threshold: 0.92
  maxsize_per_function: 1000
```

### Decorator Options

```python
@semantic_cached(
    ttl=300,                      # Seconds until cache entry expires
    similarity_threshold=0.92,    # Cosine similarity threshold (0-1)
    maxsize=1000,                 # Maximum cached entries
    invalidate_on=["file.py"],    # Files that trigger invalidation on change
)
async def my_tool(query: str) -> dict:
    ...
```

## Metrics

Access cache metrics at `/api/cache/metrics`:

```json
{
  "tools.web.get_webpage.get_webpage": {
    "hits": 45,
    "misses": 12,
    "semantic_hits": 8
  }
}
```

## Cache Invalidation

- **TTL**: Automatic expiration after configured time
- **File Changes**: Monitored files trigger cache clear on modification
- **Manual**: POST to `/api/cache/clear`

## Best Practices

1. Use higher thresholds (0.95+) for precise operations (file reads)
2. Use lower thresholds (0.85-0.90) for web search and browsing
3. Set TTL based on data volatility (web: longer, files: shorter)
4. Monitor metrics to tune thresholds for your use case
```

---

## Implementation Checklist

### Phase 1: Infrastructure
- [ ] Create `utils/semantic_cache.py` with core classes
- [ ] Add `sentence-transformers` and `numpy` to dependencies
- [ ] Test imports work: `python -c "from utils.semantic_cache import SemanticCache"`

### Phase 2: Decorator
- [ ] Implement `@semantic_cached` decorator
- [ ] Add TTL and threshold support
- [ ] Add file-based invalidation
- [ ] Add metrics tracking

### Phase 3: Tool Integration
- [ ] Apply to `get_webpage` (1 hour TTL, 0.90 threshold)
- [ ] Apply to `search_google` (30 min TTL, 0.85 threshold)
- [ ] Apply to `read_file` (1 min TTL, 0.95 threshold)

### Phase 4: Metrics
- [ ] Create `server/cache_metrics.py`
- [ ] Add `/api/cache/metrics` endpoint
- [ ] Add `/api/cache/clear` endpoint
- [ ] Integrate into `aiohttp_app.py`

### Phase 5: Testing
- [ ] Unit tests for `SemanticCache`
- [ ] Tests for `@semantic_cached` decorator
- [ ] Integration tests for cached tools
- [ ] Test metrics tracking

### Phase 6: Configuration
- [ ] Add `semantic_cache` section to `config.yaml`
- [ ] Create config loader for cache settings
- [ ] Wire decorator to use config values

### Phase 7: Documentation
- [ ] Write `docs/SEMANTIC_CACHE.md`
- [ ] Update main README with cache feature
- [ ] Add inline docstrings to all new code

---

## Success Metrics

1. **Performance**: 
   - 80%+ cache hit rate for repetitive queries
   - <10ms overhead for semantic matching
   
2. **Accuracy**:
   - No false positives at 0.95+ threshold
   - <5% false negative rate
   
3. **Resource Usage**:
   - <100MB memory per 1000 cached entries
   - <100ms model load time

---

## Notes

- The `all-MiniLM-L6-v2` model is ~80MB and provides good quality/speed tradeoff
- First call to a cached function will be slower due to model loading (~1-2s)
- Consider warming the cache for common queries at startup
- The embedding model is shared across all cached functions to reduce memory
