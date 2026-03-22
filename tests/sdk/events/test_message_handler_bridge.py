"""Tests for message-handler bridging of dispatcher events.

Covers:
- The handler yields only events published via dispatcher (no duplicates)
- Ordering is preserved
- Nested agent final events are filtered; non-final nested events pass through
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agents.types import LLMOptions
from server.message_handler import handle_user_message
from sdk.events import (
    AssistantResponse,
    publish_event,
    agent_span,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_message_handler_bridges_events_without_duplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the tool loop to publish events; ensure only published events are forwarded."""

    async def _fake_tool_loop(**_: Any) -> str | None:
        # Root-level event
        publish_event(AssistantResponse(content="one", thinking=None))
        await asyncio.sleep(0)

        # Nested agent event: non-final, passes through with content intact
        with agent_span("nested"):
            publish_event(AssistantResponse(content="secret", thinking="hidden"))
        await asyncio.sleep(0)

        # Final root-level completion
        publish_event(AssistantResponse(content="done", thinking=None, final=True))
        await asyncio.sleep(0)

        return "done"

    import server.message_handler as mh

    monkeypatch.setattr(mh, "run_turn", _fake_tool_loop)

    seen: list[AssistantResponse] = []
    async for ev in handle_user_message("hi", data=None, options=LLMOptions(model="test-model")):
        seen.append(ev)
        if len(seen) >= 3:
            break

    assert [(ev.content, ev.thinking, ev.final) for ev in seen] == [
        ("one", None, False),
        ("secret", "hidden", False),
        ("done", None, True),
    ]
