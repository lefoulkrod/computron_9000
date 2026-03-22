"""Unit tests for turn lifecycle management.

These tests validate that:
- is_turn_active returns False when no turn_scope is active
- is_turn_active returns True inside a turn_scope
- Nudge queuing and draining works within a turn_scope
- Nudge queue is cleaned up after turn_scope exits
"""

from __future__ import annotations

import pytest

from sdk.turn import (
    drain_nudges,
    is_turn_active,
    queue_nudge,
    turn_scope,
)


@pytest.mark.unit
def test_is_turn_active_outside_context() -> None:
    """is_turn_active returns False when no turn_scope is active."""
    assert is_turn_active("nonexistent") is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_is_turn_active_inside_context() -> None:
    """is_turn_active returns True while turn_scope is active."""
    async with turn_scope(conversation_id="test-sid"):
        assert is_turn_active("test-sid") is True
    assert is_turn_active("test-sid") is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_queue_and_drain_nudges() -> None:
    """Queued nudges are returned by drain_nudges and cleared."""
    async with turn_scope(conversation_id="nudge-test"):
        queue_nudge("nudge-test", "hello")
        queue_nudge("nudge-test", "world")
        result = drain_nudges()
        assert result == ["hello", "world"]
        # Second drain should be empty
        assert drain_nudges() == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_drain_nudges_empty_without_context() -> None:
    """drain_nudges returns empty list when called outside turn_scope."""
    assert drain_nudges() == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_nudge_queue_cleaned_up_after_context() -> None:
    """Nudge queue is removed when turn_scope exits."""
    async with turn_scope(conversation_id="cleanup-test"):
        queue_nudge("cleanup-test", "msg")
    # Queue should not exist after context exits
    assert drain_nudges() == []


@pytest.mark.unit
def test_queue_nudge_noop_without_context() -> None:
    """queue_nudge is a no-op when no turn_scope is active for that session."""
    queue_nudge("no-such-session", "should be dropped")
    # Nothing to assert — just ensure no exception
