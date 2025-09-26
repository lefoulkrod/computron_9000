"""Unit tests for EventDispatcher behavior.

Covers:
- subscribe/unsubscribe mechanics
- async context manager subscription cleanup
- mixed sync/async handler scheduling without blocking
- reset behavior
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agents.ollama.sdk.events import AssistantResponse, EventDispatcher


@pytest.mark.unit
@pytest.mark.asyncio
async def test_publish_to_sync_and_async_handlers(monkeypatch: Any) -> None:
    """Dispatcher should schedule both sync and async handlers."""

    dispatcher = EventDispatcher()

    seen_sync: list[AssistantResponse] = []
    seen_async: list[AssistantResponse] = []

    def sync_handler(evt: AssistantResponse) -> None:
        seen_sync.append(evt)

    async def async_handler(evt: AssistantResponse) -> None:
        await asyncio.sleep(0)  # yield control to ensure scheduling works
        seen_async.append(evt)

    dispatcher.subscribe(sync_handler)
    dispatcher.subscribe(async_handler)

    evt = AssistantResponse(content="hi")
    dispatcher.publish(evt)

    # Wait deterministically for async handlers
    await dispatcher.drain()

    assert seen_sync == [evt]
    assert seen_async == [evt]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_subscription_context_manager_auto_unsubscribes() -> None:
    """The async context manager should remove the handler on exit."""

    dispatcher = EventDispatcher()

    calls: list[str] = []

    def handler(evt: AssistantResponse) -> None:  # noqa: ARG001 - unused
        calls.append("called")

    async with dispatcher.subscription(handler):
        dispatcher.publish(AssistantResponse(content="one"))
        # Yield once so loop.call_soon scheduled sync handler executes.
        await asyncio.sleep(0)
        await dispatcher.drain()

    # After exit, publishing should not call handler again
    dispatcher.publish(AssistantResponse(content="two"))
    await asyncio.sleep(0)
    await dispatcher.drain()

    assert calls == ["called"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unsubscribe_is_idempotent() -> None:
    """Unsubscribing the same handler twice should not raise."""

    dispatcher = EventDispatcher()

    def handler(evt: AssistantResponse) -> None:  # noqa: ARG001 - unused
        pass

    dispatcher.subscribe(handler)
    dispatcher.unsubscribe(handler)
    dispatcher.unsubscribe(handler)  # should be a no-op


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reset_clears_subscribers() -> None:
    """Resetting should remove all subscribers so publish becomes a no-op."""

    dispatcher = EventDispatcher()
    seen: list[AssistantResponse] = []

    def handler(evt: AssistantResponse) -> None:
        seen.append(evt)

    dispatcher.subscribe(handler)
    dispatcher.reset()

    dispatcher.publish(AssistantResponse(content="ignored"))
    await dispatcher.drain()
    assert seen == []
@pytest.mark.unit
@pytest.mark.asyncio
async def test_drain_waits_for_inflight_tasks() -> None:
    """drain should wait for all currently scheduled async handlers to complete."""

    dispatcher = EventDispatcher()
    order: list[str] = []

    async def slow(evt: AssistantResponse) -> None:  # noqa: ARG001 - value not used
        await asyncio.sleep(0.01)
        order.append("slow")

    def fast(evt: AssistantResponse) -> None:  # noqa: ARG001 - value not used
        order.append("fast")

    dispatcher.subscribe(slow)
    dispatcher.subscribe(fast)
    dispatcher.publish(AssistantResponse(content="x"))

    # Without drain, order might not include slow yet; with drain it must.
    await dispatcher.drain()
    assert set(order) == {"fast", "slow"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_drain_is_idempotent_when_no_tasks() -> None:
    """Calling drain repeatedly with no in-flight tasks should return quickly."""

    dispatcher = EventDispatcher()
    await dispatcher.drain()  # nothing scheduled
    # Schedule a task then drain twice
    async def h(evt: AssistantResponse) -> None:  # noqa: D401, ARG001
        await asyncio.sleep(0)

    dispatcher.subscribe(h)
    dispatcher.publish(AssistantResponse(content="y"))
    await dispatcher.drain()
    await dispatcher.drain()  # second call should be a no-op


@pytest.mark.unit
@pytest.mark.asyncio
async def test_drain_does_not_raise_on_handler_error() -> None:
    """Exceptions inside handler tasks are logged but drain should still complete."""

    dispatcher = EventDispatcher()
    executed: list[str] = []

    async def bad(evt: AssistantResponse) -> None:  # noqa: ARG001
        executed.append("bad")
        raise RuntimeError("boom")

    async def good(evt: AssistantResponse) -> None:  # noqa: ARG001
        executed.append("good")
        await asyncio.sleep(0)

    dispatcher.subscribe(bad)
    dispatcher.subscribe(good)
    dispatcher.publish(AssistantResponse(content="err"))
    await dispatcher.drain()

    assert set(executed) == {"bad", "good"}
