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
    get_current_dispatcher,
    publish_event,
    reset_current_dispatcher,
    set_current_dispatcher,
)


class _DummyDispatcher:
    def __init__(self) -> None:
        self.published: list[AssistantResponse] = []

    def publish(self, event: AssistantResponse) -> None:
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
        assert d.published == [evt]
    finally:
        reset_current_dispatcher(token)
