"""Unit tests for ``server.message_handler`` cache + persistence behavior."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from conversations._store import save_conversation_history
from sdk.context import ConversationHistory
from server import message_handler as mh


@pytest.fixture(autouse=True)
def _clear_in_memory_conversations() -> Iterator[None]:
    """Reset the module-global conversation cache between tests."""
    mh._conversations.clear()
    yield
    mh._conversations.clear()


@pytest.mark.unit
def test_get_conversation_cold_cache_no_disk_creates_empty_and_marks_new() -> None:
    """No in-memory entry, no on-disk history → empty + is_new=True."""
    conv, is_new = mh._get_conversation("brand-new-id")
    assert len(conv.history) == 0
    assert conv.history.instance_id == "brand-new-id"
    assert is_new is True


@pytest.mark.unit
def test_get_conversation_cold_cache_with_disk_hydrates_and_marks_not_new() -> None:
    """No in-memory entry, on-disk history present → hydrated + is_new=False."""
    save_conversation_history("existing", [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ])

    conv, is_new = mh._get_conversation("existing")

    assert len(conv.history) == 2
    loaded = conv.history.messages
    assert loaded[0]["content"] == "hello"
    assert loaded[1]["content"] == "hi"
    assert is_new is False


@pytest.mark.unit
def test_get_conversation_warm_cache_does_not_reread_disk() -> None:
    """An in-memory entry wins over whatever is on disk and is_new=False."""
    cached = mh._Conversation(
        history=ConversationHistory(
            [{"role": "user", "content": "from-memory"}],
            instance_id="cid",
        ),
    )
    mh._conversations["cid"] = cached
    save_conversation_history("cid", [{"role": "user", "content": "from-disk"}])

    conv, is_new = mh._get_conversation("cid")

    assert conv is cached
    assert conv.history.messages[0]["content"] == "from-memory"
    assert is_new is False


@pytest.mark.unit
def test_get_conversation_subsequent_call_returns_same_instance() -> None:
    """Two calls for the same id return the same _Conversation object.

    First call mints (is_new=True), second hits the cache (is_new=False).
    """
    first, first_new = mh._get_conversation("same-id")
    second, second_new = mh._get_conversation("same-id")
    assert first is second
    assert first_new is True
    assert second_new is False


@pytest.mark.unit
def test_get_conversation_empty_id_raises() -> None:
    """Empty string is rejected — callers must supply a real id."""
    with pytest.raises(ValueError, match="conversation_id is required"):
        mh._get_conversation("")


@pytest.mark.unit
def test_get_conversation_corrupted_history_falls_back_to_empty(tmp_path: Path) -> None:
    """A malformed history.json is treated as no on-disk history.

    ``load_conversation_history`` swallows JSON parse errors and returns
    None; ``_get_conversation`` then mints a fresh empty history. This
    keeps the chat path live rather than 500ing on a corrupted file.
    """
    from conversations._store import _get_conversations_dir

    cid = "corrupted"
    conv_dir = _get_conversations_dir() / cid
    conv_dir.mkdir(parents=True)
    (conv_dir / "history.json").write_text("{not valid json", encoding="utf-8")

    conv, is_new = mh._get_conversation(cid)

    assert len(conv.history) == 0
    assert is_new is True


@pytest.mark.unit
def test_lru_evicts_oldest_when_cap_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inserting beyond the cap evicts the least-recently-used entry."""
    monkeypatch.setattr(mh, "_MAX_CACHED_CONVERSATIONS", 3)

    mh._get_conversation("a")
    mh._get_conversation("b")
    mh._get_conversation("c")
    assert list(mh._conversations) == ["a", "b", "c"]

    mh._get_conversation("d")

    assert "a" not in mh._conversations
    assert list(mh._conversations) == ["b", "c", "d"]


@pytest.mark.unit
def test_lru_access_promotes_to_most_recently_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cache hit moves the entry to the end so it survives the next eviction."""
    monkeypatch.setattr(mh, "_MAX_CACHED_CONVERSATIONS", 3)

    mh._get_conversation("a")
    mh._get_conversation("b")
    mh._get_conversation("c")

    # Touch 'a' — should become most-recently-used.
    mh._get_conversation("a")
    assert list(mh._conversations) == ["b", "c", "a"]

    # Inserting a fourth should now evict 'b', not 'a'.
    mh._get_conversation("d")
    assert "b" not in mh._conversations
    assert "a" in mh._conversations


@pytest.mark.unit
def test_lru_skips_active_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Conversations whose turn is in flight are not evicted."""
    monkeypatch.setattr(mh, "_MAX_CACHED_CONVERSATIONS", 2)
    monkeypatch.setattr(mh, "is_turn_active", lambda cid: cid == "a")

    mh._get_conversation("a")  # pinned
    mh._get_conversation("b")
    assert list(mh._conversations) == ["a", "b"]

    # Inserting 'c' would normally evict 'a' (oldest). Pinning skips
    # over 'a' and evicts 'b' instead.
    mh._get_conversation("c")
    assert "a" in mh._conversations
    assert "b" not in mh._conversations
    assert "c" in mh._conversations


@pytest.mark.unit
def test_lru_overflow_when_all_active(monkeypatch: pytest.MonkeyPatch) -> None:
    """When every cached conv is mid-turn, the cache temporarily overflows."""
    monkeypatch.setattr(mh, "_MAX_CACHED_CONVERSATIONS", 2)
    monkeypatch.setattr(mh, "is_turn_active", lambda _cid: True)

    mh._get_conversation("a")
    mh._get_conversation("b")
    mh._get_conversation("c")  # over cap, but no eviction possible

    assert len(mh._conversations) == 3
    assert set(mh._conversations) == {"a", "b", "c"}


@pytest.mark.unit
def test_lru_does_not_evict_just_inserted_when_others_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Just-inserted conv survives even when every existing entry is mid-turn.

    The caller has not yet entered ``turn_scope`` for the new conv, so
    ``is_turn_active`` returns False for it. Without the ``exclude`` guard
    in ``_evict_lru``, the loop would walk past every pinned active entry
    and evict the just-inserted one — surprising behavior that defeats
    the point of the cache miss.
    """
    monkeypatch.setattr(mh, "_MAX_CACHED_CONVERSATIONS", 2)
    # Only pre-existing convs ('a', 'b') are active. The new one ('c')
    # is treated as inactive — matches reality at _get_conversation time.
    monkeypatch.setattr(mh, "is_turn_active", lambda cid: cid in {"a", "b"})

    mh._get_conversation("a")
    mh._get_conversation("b")
    mh._get_conversation("c")

    assert "c" in mh._conversations
    assert set(mh._conversations) == {"a", "b", "c"}


@pytest.mark.unit
def test_resume_conversation_marks_most_recently_used() -> None:
    """resume_conversation places the resumed entry at the LRU tail."""
    mh._get_conversation("a")
    save_conversation_history("from-disk", [{"role": "user", "content": "hi"}])

    result = mh.resume_conversation("from-disk")

    assert result is not None
    # 'from-disk' should now be the most-recently-used (last in order).
    assert list(mh._conversations)[-1] == "from-disk"
