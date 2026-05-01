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
def test_reset_message_history_evicts_in_memory_entry() -> None:
    """reset_message_history drops the in-memory cache for the id."""
    mh._get_conversation("to-evict")
    assert "to-evict" in mh._conversations

    mh.reset_message_history("to-evict")

    assert "to-evict" not in mh._conversations


@pytest.mark.unit
def test_reset_message_history_preserves_disk() -> None:
    """reset_message_history does not delete on-disk history.

    Subsequent _get_conversation should re-hydrate from disk.
    """
    save_conversation_history("survives", [{"role": "user", "content": "x"}])
    mh._get_conversation("survives")

    mh.reset_message_history("survives")

    conv, is_new = mh._get_conversation("survives")
    assert is_new is False
    assert conv.history.messages[0]["content"] == "x"


@pytest.mark.unit
def test_reset_message_history_empty_id_raises() -> None:
    """Empty string is rejected."""
    with pytest.raises(ValueError, match="conversation_id is required"):
        mh.reset_message_history("")
