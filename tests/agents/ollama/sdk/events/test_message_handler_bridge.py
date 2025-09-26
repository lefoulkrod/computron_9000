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
from agents.ollama.sdk.events import AssistantResponse, publish_event


@pytest.mark.unit
@pytest.mark.asyncio
async def test_message_handler_bridges_events_without_duplicates(monkeypatch):
    """Patch the tool loop to both publish events and yield values; ensure only published events are forwarded."""

    # Scripted published events
    published: List[AssistantResponse] = [
        AssistantResponse(content="one", thinking=None),
        AssistantResponse(content="two", thinking="t"),
    ]

    async def _fake_tool_loop(**_: Any) -> AsyncGenerator[tuple[str | None, str | None], None]:  # noqa: D401
        # Publish the scripted events into the current event_context
        for evt in published:
            publish_event(evt)
            # Underlying generator still yields something (ignored by handler)
            yield (evt.content, evt.thinking)
            # Yield to event loop; publish creates tasks handled externally.
            await asyncio.sleep(0)

    # Patch where it's imported in the message handler module
    import agents.ollama.message_handler as mh

    monkeypatch.setattr(mh, "run_tool_call_loop", _fake_tool_loop)

    # Collect events from the handler
    seen: list[tuple[str | None, str | None]] = []
    async for ev in handle_user_message("hi", data=None):
        seen.append((ev.content, ev.thinking))
        # Stop after we've seen the two expected events to avoid looping
        if len(seen) >= 2:
            break

    # We should see exactly the published events, in order, and no duplicates
    assert seen == [("one", None), ("two", "t")]
