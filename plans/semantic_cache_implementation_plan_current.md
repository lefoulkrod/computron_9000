# Implementation Plan: Intelligent Tool Result Caching with Semantic Matching

## Current Branch: improvement/20260401-semantic-tool-caching

## Phase 1: Core Cache Infrastructure
- [x] Create `utils/semantic_cache.py` with core classes
- [x] Add `sentence-transformers` and `numpy` to dependencies (numpy already available)

## Phase 2: The `@semantic_cached` Decorator
- [x] Extend `utils/semantic_cache.py` with decorator
- [x] Add TTL and threshold support
- [x] Add metrics tracking

## Phase 3: Apply Caching to Tool Functions
- [x] Modify `tools/web/get_webpage.py` 
- [x] Modify `tools/web/search_google.py`
- Note: `read_file` is sync, will skip for now or add sync support

## Phase 4: Cache Metrics and Observability
- [x] Create `server/cache_metrics.py`
- [x] Update `server/aiohttp_app.py` to add routes

## Phase 5: Testing
- [ ] Create `tests/utils/test_semantic_cache.py`
- [ ] Create `tests/tools/test_cached_tools.py`

## Phase 6: Configuration
- [ ] Update `config.yaml` with semantic_cache section

## Phase 7: Documentation
- [ ] Create `docs/SEMANTIC_CACHE.md`
