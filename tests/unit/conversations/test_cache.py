"""Unit tests for ``conversations.ConversationCache``."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from conversations import ConversationCache
from conversations._store import save_conversation_history
from sdk import Conversation
from sdk.context import ConversationHistory


@pytest.fixture
async def cache() -> AsyncIterator[ConversationCache]:
    """A fresh cache, no active-turn awareness, no on-evict side effect."""
    c = ConversationCache()
    yield c
    c.clear()


# ---------------------------------------------------------------------------
# get() — hydration semantics
# ---------------------------------------------------------------------------


async def test_get_cold_no_disk_creates_empty_and_marks_new(cache: ConversationCache) -> None:
    conv, is_new = await cache.get("brand-new-id")
    assert len(conv.history) == 0
    assert conv.history.instance_id == "brand-new-id"
    assert is_new is True


async def test_get_cold_with_disk_hydrates_and_marks_not_new(cache: ConversationCache) -> None:
    save_conversation_history("existing", [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ])
    conv, is_new = await cache.get("existing")
    assert len(conv.history) == 2
    loaded = conv.history.messages
    assert loaded[0]["content"] == "hello"
    assert loaded[1]["content"] == "hi"
    assert is_new is False


async def test_warm_cache_wins_over_disk(cache: ConversationCache) -> None:
    """An in-memory entry wins over whatever is on disk and is_new=False."""
    cached = Conversation(
        id="cid",
        history=ConversationHistory(
            [{"role": "user", "content": "from-memory"}],
            instance_id="cid",
        ),
    )
    cache._entries["cid"] = cached
    save_conversation_history("cid", [{"role": "user", "content": "from-disk"}])

    conv, is_new = await cache.get("cid")
    assert conv is cached
    assert conv.history.messages[0]["content"] == "from-memory"
    assert is_new is False


async def test_subsequent_call_returns_same_instance(cache: ConversationCache) -> None:
    first, first_new = await cache.get("same-id")
    second, second_new = await cache.get("same-id")
    assert first is second
    assert first_new is True
    assert second_new is False


async def test_empty_id_raises(cache: ConversationCache) -> None:
    with pytest.raises(ValueError, match="conversation_id is required"):
        await cache.get("")


async def test_corrupted_history_falls_back_to_empty(
    cache: ConversationCache, tmp_path: Path,
) -> None:
    from conversations._store import _get_conversations_dir

    cid = "corrupted"
    conv_dir = _get_conversations_dir() / cid
    conv_dir.mkdir(parents=True)
    (conv_dir / "history.json").write_text("{not valid json", encoding="utf-8")

    conv, is_new = await cache.get(cid)
    assert len(conv.history) == 0
    assert is_new is True


# ---------------------------------------------------------------------------
# LRU + eviction
# ---------------------------------------------------------------------------


async def test_lru_evicts_oldest_when_cap_exceeded() -> None:
    cache = ConversationCache(max_size=3)
    for cid in ("a", "b", "c"):
        await cache.get(cid)
    assert list(cache) == ["a", "b", "c"]

    await cache.get("d")
    assert "a" not in cache
    assert list(cache) == ["b", "c", "d"]


async def test_lru_access_promotes_to_most_recently_used() -> None:
    cache = ConversationCache(max_size=3)
    for cid in ("a", "b", "c"):
        await cache.get(cid)

    # Touch 'a' — should become most-recently-used.
    await cache.get("a")
    assert list(cache) == ["b", "c", "a"]

    # Inserting a fourth should now evict 'b', not 'a'.
    await cache.get("d")
    assert "b" not in cache
    assert "a" in cache


async def test_lru_skips_active_turn() -> None:
    active = {"a"}
    cache = ConversationCache(max_size=2, is_active=lambda cid: cid in active)

    await cache.get("a")
    await cache.get("b")
    assert list(cache) == ["a", "b"]

    # Inserting 'c' would normally evict 'a' (oldest). Active-skip jumps
    # over 'a' and evicts 'b' instead.
    await cache.get("c")
    assert "a" in cache
    assert "b" not in cache
    assert "c" in cache


async def test_lru_overflow_when_all_active() -> None:
    cache = ConversationCache(max_size=2, is_active=lambda _cid: True)
    await cache.get("a")
    await cache.get("b")
    await cache.get("c")
    assert len(cache) == 3
    assert set(cache) == {"a", "b", "c"}


async def test_lru_does_not_evict_just_inserted_when_others_active() -> None:
    """Just-inserted survives even when every existing entry is mid-turn."""
    pinned = {"a", "b"}
    cache = ConversationCache(max_size=2, is_active=lambda cid: cid in pinned)
    await cache.get("a")
    await cache.get("b")
    await cache.get("c")
    assert "c" in cache
    assert set(cache) == {"a", "b", "c"}


# ---------------------------------------------------------------------------
# on_evict callback
# ---------------------------------------------------------------------------


async def test_on_evict_fires_with_evicted_id() -> None:
    evicted: list[str] = []

    async def _on_evict(cid: str) -> None:
        evicted.append(cid)

    cache = ConversationCache(max_size=2, on_evict=_on_evict)
    await cache.get("a")
    await cache.get("b")
    await cache.get("c")
    assert evicted == ["a"]


# ---------------------------------------------------------------------------
# resume() — force-reload
# ---------------------------------------------------------------------------


async def test_resume_returns_none_for_missing(cache: ConversationCache) -> None:
    assert await cache.resume("nope") is None


async def test_resume_hydrates_and_marks_most_recently_used() -> None:
    cache = ConversationCache(max_size=3)
    await cache.get("a")
    save_conversation_history(
        "from-disk", [{"role": "user", "content": "hi"}],
    )
    conv = await cache.resume("from-disk")
    assert conv is not None
    # 'from-disk' is now most-recently-used.
    assert list(cache)[-1] == "from-disk"


async def test_resume_overwrites_cached_entry(cache: ConversationCache) -> None:
    """resume reloads from disk even if a cached entry exists for the id."""
    save_conversation_history(
        "twice", [{"role": "user", "content": "first version"}],
    )
    first = await cache.resume("twice")
    assert first is not None
    assert first.history.messages[0]["content"] == "first version"

    save_conversation_history(
        "twice", [{"role": "user", "content": "second version"}],
    )
    second = await cache.resume("twice")
    assert second is not None
    assert second is not first
    assert second.history.messages[0]["content"] == "second version"


# ---------------------------------------------------------------------------
# pop()
# ---------------------------------------------------------------------------


async def test_pop_drops_entry(cache: ConversationCache) -> None:
    await cache.get("a")
    assert "a" in cache
    cache.pop("a")
    assert "a" not in cache


def test_pop_unknown_id_is_a_no_op(cache: ConversationCache) -> None:
    cache.pop("never-existed")  # should not raise
