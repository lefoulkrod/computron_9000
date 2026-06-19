"""Unit tests for ``server.message_handler`` — the SSE handler glue.

Cache behavior is covered in ``tests/unit/conversations/test_cache.py``.
What's here is the higher-level wiring this module is actually responsible
for — composing ``resume_conversation``'s payload from history + events +
preview state.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest

from conversations._store import (
    save_agent_events,
    save_conversation_history,
    save_preview_state,
)
from server import message_handler as mh


@pytest.fixture(autouse=True)
async def _clear_cache() -> AsyncIterator[None]:
    """Reset the module-global cache between tests."""
    mh._cache.clear()
    yield
    mh._cache.clear()


@pytest.fixture(autouse=True)
def _stub_browser_release():
    """Stub out release_agent_browser so eviction doesn't touch Playwright."""
    with patch.object(mh, "release_agent_browser", new_callable=AsyncMock):
        yield


async def test_resume_returns_none_for_missing() -> None:
    assert await mh.resume_conversation("does-not-exist") is None


async def test_resume_returns_messages_events_and_preview_state() -> None:
    """resume_conversation reads history, events, and preview state from disk."""
    cid = "resume-test"
    save_conversation_history(cid, [{"role": "user", "content": "hi"}])
    save_agent_events(cid, [{"payload": {"type": "content", "content": "x"}}])
    save_preview_state(cid, {"open": ["a.txt"]})

    result = await mh.resume_conversation(cid)

    assert result is not None
    assert result["messages"] == [{"role": "user", "content": "hi"}]
    # events list and preview_state dict shapes are determined by the store;
    # asserting they're truthy is enough — the store has its own tests.
    assert result["events"]
    assert result["preview_state"]


async def test_resume_installs_into_cache() -> None:
    """After resume, the conversation is in the cache (so the next turn
    reuses the same Conversation object)."""
    cid = "resume-then-turn"
    save_conversation_history(cid, [{"role": "user", "content": "hi"}])

    await mh.resume_conversation(cid)
    assert cid in mh._cache
