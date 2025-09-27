"""Unit tests for context-bound event publishing utilities.

These tests validate that:
- publish_event is a no-op when no dispatcher is set
- set/reset correctly bind and restore the current dispatcher
- publish_event delegates to the active dispatcher's publish method
"""

from __future__ import annotations

from typing import Any

import pytest

from agents.ollama.sdk.events import (
    AssistantResponse,
    DispatchEvent,
    get_current_dispatcher,
    make_child_context_id,
    publish_event,
    reset_current_dispatcher,
    set_current_dispatcher,
    use_context_id,
)


class _DummyDispatcher:
    def __init__(self) -> None:
        self.published: list[DispatchEvent] = []

    def publish(self, event: DispatchEvent) -> None:
        self.published.append(event)


@pytest.mark.unit
def test_publish_event_noop_without_dispatcher() -> None:
    """Calling publish_event without a dispatcher should not raise or mutate state."""
    # Ensure no dispatcher is set
    token = set_current_dispatcher(None)
    try:
        publish_event(AssistantResponse(content="hi"))
    finally:
        reset_current_dispatcher(token)


@pytest.mark.unit
def test_set_and_reset_current_dispatcher() -> None:
    """set_current_dispatcher returns a token that can restore the previous value."""
    # Start with a clean slate
    root_token = set_current_dispatcher(None)
    try:
        assert get_current_dispatcher() is None
        d = _DummyDispatcher()
        token = set_current_dispatcher(d)
        try:
            assert get_current_dispatcher() is d
        finally:
            reset_current_dispatcher(token)
        assert get_current_dispatcher() is None
    finally:
        reset_current_dispatcher(root_token)


@pytest.mark.unit
def test_publish_event_delegates_to_dispatcher() -> None:
    """publish_event should invoke publish on the bound dispatcher with the same event."""
    d = _DummyDispatcher()
    token = set_current_dispatcher(d)
    try:
        evt = AssistantResponse(content="hello")
        publish_event(evt)
        assert len(d.published) == 1
        dispatch_evt = d.published[0]
        assert dispatch_evt.payload is evt
        assert dispatch_evt.context_id
    finally:
        reset_current_dispatcher(token)


@pytest.mark.unit
def test_child_context_ids_form_hierarchy() -> None:
    """Child context ids should extend their parent ids deterministically."""

    token = set_current_dispatcher(None)
    with use_context_id("root") as root_id:
        child_id = make_child_context_id("nested")
        assert child_id.startswith(root_id)
        with use_context_id(child_id) as resolved_child:
            grandchild_id = make_child_context_id("deep")
            assert grandchild_id.startswith(resolved_child)
    reset_current_dispatcher(token)
