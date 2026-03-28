"""Tests for message-handler bridging of dispatcher events.

Covers:
- The handler yields only events published via dispatcher (no duplicates)
- Ordering is preserved
- Agent lifecycle events (agent_started, agent_completed) are emitted by agent_span
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agents.types import LLMOptions
from server.message_handler import handle_user_message
from sdk.events import (
    AgentCompletedPayload,
    AgentStartedPayload,
    AgentEvent,
    ContentPayload,
    TurnEndPayload,
    publish_event,
    agent_span,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_message_handler_bridges_events_without_duplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the tool loop to publish events; ensure published events are forwarded
    including lifecycle events from agent_span.
    """

    async def _fake_tool_loop(**_: Any) -> str | None:
        # Root-level event
        publish_event(AgentEvent(payload=ContentPayload(type="content", content="one")))
        await asyncio.sleep(0)

        # Nested agent event: passes through with content intact
        with agent_span("nested"):
            publish_event(AgentEvent(payload=ContentPayload(type="content", content="secret", thinking="hidden")))
        await asyncio.sleep(0)

        # Turn end
        publish_event(AgentEvent(payload=TurnEndPayload(type="turn_end")))
        await asyncio.sleep(0)

        return "done"

    import server.message_handler as mh

    monkeypatch.setattr(mh, "run_turn", _fake_tool_loop)

    seen: list[AgentEvent] = []
    async for ev in handle_user_message("hi", data=None, options=LLMOptions(model="test-model")):
        seen.append(ev)
        if ev.payload.type == "turn_end":
            break

    # Filter to content events and lifecycle events
    content_events = [
        (ev.payload.content, ev.payload.thinking)
        for ev in seen
        if ev.payload.type == "content"
    ]
    lifecycle_events = [
        (ev.payload.type, ev.payload.agent_name)
        for ev in seen
        if isinstance(ev.payload, (AgentStartedPayload, AgentCompletedPayload))
    ]

    # Content events should pass through in order
    assert content_events == [
        ("one", None),
        ("secret", "hidden"),
    ]

    # Lifecycle events: root started, nested started, nested completed, root completed
    agent_names = [name for _, name in lifecycle_events]
    assert "nested" in agent_names
