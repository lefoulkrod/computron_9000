"""Tests for message-handler bridging of dispatcher events.

Covers:
- The handler yields only events published via dispatcher (no duplicates from
  the underlying generator yields)
- Ordering is preserved
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, List

import pytest

from agents.ollama.message_handler import handle_user_message
from agents.ollama.sdk.events import (
    AssistantResponse,
    make_child_context_id,
    publish_event,
    use_context_id,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_message_handler_bridges_events_without_duplicates(monkeypatch):
    """Patch the tool loop to both publish events and yield values; ensure only published events are forwarded."""

    # Scripted published events
    async def _fake_tool_loop(**_: Any) -> AsyncGenerator[tuple[str | None, str | None], None]:  # noqa: D401
        # Root-level event
        publish_event(AssistantResponse(content="one", thinking=None))
        yield ("one", None)
        await asyncio.sleep(0)

        # Nested agent/tool event should surface with blank content
        with use_context_id(make_child_context_id("nested")):
            publish_event(AssistantResponse(content="secret", thinking="hidden"))
        yield ("secret", "hidden")
        await asyncio.sleep(0)

        # Final root-level completion
        publish_event(AssistantResponse(content="done", thinking=None, final=True))
        yield ("done", None)
        await asyncio.sleep(0)

    # Patch where it's imported in the message handler module
    import agents.ollama.message_handler as mh

    monkeypatch.setattr(mh, "run_tool_call_loop", _fake_tool_loop)

    # Collect events from the handler
    seen: list[AssistantResponse] = []
    async for ev in handle_user_message("hi", data=None):
        seen.append(ev)
        # Stop after we've seen the two expected events to avoid looping
        if len(seen) >= 3:
            break

    # We should see root event, sanitized child (empty content), and final root event
    assert [(ev.content, ev.thinking, ev.final) for ev in seen] == [
        ("one", None, False),
        ("", "hidden", False),
        ("done", None, True),
    ]
