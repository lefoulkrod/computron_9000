"""Unit tests for context-bound event publishing utilities.

These tests validate that:
- publish_event is a no-op when no dispatcher is set
- _current_dispatcher can be set/reset via ContextVar directly
- publish_event delegates to the active dispatcher with the event content
"""

from __future__ import annotations

import pytest

from agents.ollama.sdk.events import (
    AssistantResponse,
    EventDispatcher,
    publish_event,
    agent_span,
)
from agents.ollama.sdk.events.context import _current_dispatcher


class _TrackingDispatcher(EventDispatcher):
    def __init__(self) -> None:
        super().__init__()
        self.published: list[AssistantResponse] = []

    def publish(self, event: AssistantResponse) -> None:
        self.published.append(event)


@pytest.mark.unit
def test_publish_event_noop_without_dispatcher() -> None:
    """Calling publish_event without a dispatcher should not raise or mutate state."""
    token = _current_dispatcher.set(None)
    try:
        publish_event(AssistantResponse(content="hi"))
    finally:
        _current_dispatcher.reset(token)


@pytest.mark.unit
def test_set_and_reset_current_dispatcher() -> None:
    """_current_dispatcher ContextVar can be set and reset via token."""
    root_token = _current_dispatcher.set(None)
    try:
        assert _current_dispatcher.get() is None
        d = _TrackingDispatcher()
        token = _current_dispatcher.set(d)
        try:
            assert _current_dispatcher.get() is d
        finally:
            _current_dispatcher.reset(token)
        assert _current_dispatcher.get() is None
    finally:
        _current_dispatcher.reset(root_token)


@pytest.mark.unit
def test_publish_event_delegates_to_dispatcher() -> None:
    """publish_event should invoke publish on the bound dispatcher with the event content."""
    d = _TrackingDispatcher()
    token = _current_dispatcher.set(d)
    try:
        publish_event(AssistantResponse(content="hello"))
        assert len(d.published) == 1
        published = d.published[0]
        assert published.content == "hello"
        assert published.depth is not None
    finally:
        _current_dispatcher.reset(token)


@pytest.mark.unit
def test_child_context_ids_form_hierarchy() -> None:
    """Child context ids should extend their parent ids deterministically."""
    with agent_span(context_id="root") as root_id:
        with agent_span("nested") as child_id:
            assert child_id.startswith(root_id)
            with agent_span("deep") as grandchild_id:
                assert grandchild_id.startswith(child_id)
