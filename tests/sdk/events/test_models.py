"""Unit tests for events models.

These tests validate the AgentEvent schema, the discriminated union for
event payloads, default values, and JSON-serializable output shape.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from sdk.events import (
    AgentEvent,
    AgentEventData,
    ToolCallPayload,
)


@pytest.mark.unit
def test_assistant_response_defaults():
    """AgentEvent should initialize with sensible defaults.

    Validates that optional fields are None/empty and a timestamp is set.
    """

    before = datetime.utcnow()
    resp = AgentEvent()
    after = datetime.utcnow()

    assert resp.content is None
    assert resp.thinking is None
    assert resp.event is None
    assert isinstance(resp.data, list) and resp.data == []
    assert isinstance(resp.timestamp, datetime)
    # timestamp should be within the test window
    assert before - timedelta(seconds=1) <= resp.timestamp <= after + timedelta(seconds=1)


@pytest.mark.unit
def test_tool_call_event_embedding():
    """Embedding a ToolCallPayload inside AgentEvent should be valid.

    Also ensures serialization retains the discriminator for the event payload.
    """

    payload = ToolCallPayload(type="tool_call", name="web_search")
    resp = AgentEvent(event=payload, content=None)

    assert resp.event is not None
    assert resp.event.type == "tool_call"
    assert resp.event.name == "web_search"

    as_dict = resp.model_dump()
    assert as_dict["event"]["type"] == "tool_call"
    assert as_dict["event"]["name"] == "web_search"


@pytest.mark.unit
def test_response_data_attachment():
    """AgentEventData items can be attached and serialized."""

    data = AgentEventData(content_type="image/png", content="iVBORw0KGgoAAAANSUhEUg==")
    resp = AgentEvent(data=[data])

    assert len(resp.data) == 1
    assert resp.data[0].content_type == "image/png"
    assert isinstance(resp.data[0].content, str)

    dumped = resp.model_dump()
    assert dumped["data"][0]["content_type"] == "image/png"
    assert dumped["data"][0]["content"].startswith("iVBORw0KGgo")
