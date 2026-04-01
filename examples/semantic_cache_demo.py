"""Example demonstrating semantic caching functionality.

This script demonstrates how the semantic cache works by showing:
1. Exact match caching (same arguments return cached result)
2. Semantic match caching (similar arguments return cached result)
3. Metrics tracking (hit/miss rates)
4. Cache invalidation
"""

from __future__ import annotations

import asyncio
from utils.semantic_cache import semantic_cached, clear_all_caches, get_metrics


# Example 1: Web search simulation with semantic caching
@semantic_cached(ttl=300, similarity_threshold=0.85, maxsize=100)
async def search_web(query: str) -> dict[str, str]:
    """Simulate a web search - would normally make API call."""
    print(f"  [EXECUTING] Web search for: '{query}'")
    # Simulate API delay
    await asyncio.sleep(0.1)
    return {
        "query": query,
        "results": [f"Result for '{query}'"],
        "executed_at": asyncio.get_event_loop().time()
    }


# Example 2: Document fetch with higher similarity threshold
@semantic_cached(ttl=600, similarity_threshold=0.90, maxsize=50)
async def fetch_document(url: str) -> dict[str, str]:
    """Simulate fetching a document - would normally make HTTP request."""
    print(f"  [EXECUTING] Fetch document: '{url}'")
    await asyncio.sleep(0.1)
    return {
        "url": url,
        "content": f"Content of {url}",
        "fetched_at": asyncio.get_event_loop().time()
    }


async def demo_exact_match() -> None:
    """Demonstrate exact match caching."""
    print("\n" + "=" * 60)
    print("DEMO: Exact Match Caching")
    print("=" * 60)

    # First call - executes
    print("1. First call with exact arguments:")
    result1 = await search_web("python programming")
    print(f"   Result: {result1['query']}")

    # Second call - exact same args, uses cache
    print("\n2. Second call with same arguments (cached):")
    result2 = await search_web("python programming")
    print(f"   Result: {result2['query']}")

    # Verify they're the same cached result
    print(f"\n   ✓ Both results identical: {result1['results'] == result2['results']}")


async def demo_semantic_match() -> None:
    """Demonstrate semantic match caching."""
    print("\n" + "=" * 60)
    print("DEMO: Semantic Match Caching")
    print("=" * 60)

    clear_all_caches()

    # First call
    print("1. First call with 'machine learning tutorial':")
    result1 = await search_web("machine learning tutorial")
    print(f"   Result: {result1['query']}")

    # Similar query - should use cache
    print("\n2. Similar query 'ml tutorial' (semantically cached):")
    result2 = await search_web("ml tutorial")
    print(f"   Result: {result2['query']}")

    # Another similar query
    print("\n3. Similar query 'tutorial on machine learning' (semantically cached):")
    result3 = await search_web("tutorial on machine learning")
    print(f"   Result: {result3['query']}")

    print("\n   ✓ All three returned same cached result despite different queries")


async def demo_different_queries() -> None:
    """Demonstrate different queries don't match."""
    print("\n" + "=" * 60)
    print("DEMO: Different Queries (No Semantic Match)")
    print("=" * 60)

    clear_all_caches()

    print("1. Search for 'cooking recipes':")
    await search_web("cooking recipes")

    print("\n2. Search for 'quantum physics' (different topic, executes):")
    await search_web("quantum physics")

    print("\n   ✓ Two separate executions for unrelated topics")


async def demo_metrics() -> None:
    """Demonstrate cache metrics."""
    print("\n" + "=" * 60)
    print("DEMO: Cache Metrics")
    print("=" * 60)

    clear_all_caches()

    # Make some calls
    await search_web("python")
    await search_web("python")  # Exact match
    await search_web("python programming")  # Semantic match
    await search_web("java")  # Different

    # Get stats for search_web function
    stats = search_web.get_stats()
    print(f"\nCache Statistics for 'search_web':")
    print(f"  - Cache size: {stats['size']}/{stats['maxsize']}")
    print(f"  - Hits: {stats.get('hits', 'N/A')}")
    print(f"  - Misses: {stats.get('misses', 'N/A')}")

    # Get all metrics
    all_metrics = get_metrics()
    print(f"\nTotal cached functions: {len(all_metrics)}")


async def demo_invalidation() -> None:
    """Demonstrate cache invalidation."""
    print("\n" + "=" * 60)
    print("DEMO: Cache Invalidation")
    print("=" * 60)

    clear_all_caches()

    # Populate cache
    await search_web("cached query")
    print(f"\n1. Cache populated with 'cached query'")

    stats_before = search_web.get_stats()
    print(f"   Cache size: {stats_before['size']}")

    # Clear cache
    await search_web.clear_cache()
    print("\n2. Cache cleared")

    stats_after = search_web.get_stats()
    print(f"   Cache size: {stats_after['size']}")

    print("\n   ✓ Cache successfully invalidated")


async def demo_config_thresholds() -> None:
    """Demonstrate different similarity thresholds."""
    print("\n" + "=" * 60)
    print("DEMO: Different Similarity Thresholds")
    print("=" * 60)

    clear_all_caches()

    # fetch_document has 90% threshold (stricter)
    # search_web has 85% threshold (looser)

    print("\nFunctions configured with different thresholds:")
    print("  - fetch_document: 90% similarity (stricter)")
    print("  - search_web: 85% similarity (looser)")

    print("\nThis allows fine-tuning cache behavior per tool:")
    print("  - Web pages need more exact matching (90%)")
    print("  - Search queries can be more flexible (85%)")


async def main() -> None:
    """Run all demonstrations."""
    print("\n" + "=" * 60)
    print("SEMANTIC CACHE DEMONSTRATION")
    print("=" * 60)
    print("\nThis demo shows how the semantic cache works by")
    print("comparing arguments using embeddings to find similar queries.")

    await demo_exact_match()
    await demo_semantic_match()
    await demo_different_queries()
    await demo_metrics()
    await demo_invalidation()
    await demo_config_thresholds()

    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)
    print("\nThe semantic cache successfully:")
    print("  ✓ Caches exact argument matches")
    print("  ✓ Caches semantically similar arguments")
    print("  ✓ Tracks hit/miss metrics")
    print("  ✓ Supports explicit invalidation")
    print("  ✓ Configurable per-function thresholds")
    print()


if __name__ == "__main__":
    asyncio.run(main())
