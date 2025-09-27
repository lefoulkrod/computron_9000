import asyncio
import time
from typing import Any

import pytest

from utils import cache


@pytest.mark.asyncio
async def test_concurrent_callers_share_computation() -> None:
    calls = 0

    async def worker(x: int) -> int:
        nonlocal calls
        calls += 1
        # simulate work
        await asyncio.sleep(0.01)
        return x * 2

    cached = cache.async_lru_cache()(worker)
    cache.clear_cache(worker)

    # run multiple concurrent callers with same arg
    results = await asyncio.gather(*(cached(3) for _ in range(5)))
    assert results == [6] * 5
    # underlying function should have been called once
    assert calls == 1


@pytest.mark.asyncio
async def test_non_hashable_args_raise_typeerror() -> None:
    async def worker(x: Any) -> int:
        return 1

    cached = cache.async_lru_cache()(worker)
    cache.clear_cache(worker)

    with pytest.raises(TypeError):
        await cached([1, 2, 3])  # list is unhashable


@pytest.mark.asyncio
async def test_cache_hit_avoids_recompute() -> None:
    calls = 0

    async def worker(x: int) -> int:
        nonlocal calls
        calls += 1
        return x + 1

    cached = cache.async_lru_cache()(worker)
    cache.clear_cache(worker)

    a = await cached(1)
    b = await cached(1)
    assert a == b == 2
    assert calls == 1
