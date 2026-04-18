"""Unit tests for events models.

These tests validate the AgentEvent schema, the discriminated union for
event payloads, default values, and JSON-serializable output shape.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sdk.events import (
    AgentEvent,
    ContentPayload,
    ToolCallPayload,
    TurnEndPayload,
)


@pytest.mark.unit
def test_agent_event_defaults():
    """AgentEvent should initialize with a payload and sensible defaults.

    Validates that metadata fields default to None and a timestamp is set.
    """

    before = datetime.now(UTC)
    resp = AgentEvent(payload=ContentPayload(type="content"))
    after = datetime.now(UTC)

    assert resp.payload.type == "content"
    assert resp.payload.content is None
    assert resp.agent_name is None
    assert resp.agent_id is None
    assert resp.depth is None
    assert isinstance(resp.timestamp, datetime)
    # timestamp should be within the test window
    assert before - timedelta(seconds=1) <= resp.timestamp <= after + timedelta(seconds=1)


@pytest.mark.unit
def test_tool_call_event_embedding():
    """Embedding a ToolCallPayload inside AgentEvent should be valid.

    Also ensures serialization retains the discriminator for the payload.
    """

    payload = ToolCallPayload(type="tool_call", name="web_search")
    resp = AgentEvent(payload=payload)

    assert resp.payload.type == "tool_call"
    assert resp.payload.name == "web_search"

    as_dict = resp.model_dump()
    assert as_dict["payload"]["type"] == "tool_call"
    assert as_dict["payload"]["name"] == "web_search"


@pytest.mark.unit
def test_content_payload_fields():
    """ContentPayload should carry content, thinking, and delta."""

    resp = AgentEvent(payload=ContentPayload(
        type="content",
        content="hello",
        thinking="reasoning",
        delta=True,
    ))

    assert resp.payload.content == "hello"
    assert resp.payload.thinking == "reasoning"
    assert resp.payload.delta is True


@pytest.mark.unit
def test_turn_end_payload():
    """TurnEndPayload signals end of turn."""

    resp = AgentEvent(payload=TurnEndPayload(type="turn_end"))

    as_dict = resp.model_dump()
    assert as_dict["payload"]["type"] == "turn_end"
