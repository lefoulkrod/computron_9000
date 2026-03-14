"""Tests that tool loop publishes AssistantResponse events via the dispatcher.

Covers:
- Emission of content/thinking events after a model response
- Emission of tool_call event before executing a tool
- Preservation of generator contract (still yields content, thinking)
"""

from __future__ import annotations

from typing import Any, List

import pytest

from sdk.context import ConversationHistory
from sdk.events import AssistantResponse, ToolCallPayload
from sdk.providers._models import ChatMessage, ChatResponse, TokenUsage, ToolCall, ToolCallFunction
from sdk.loop import run_tool_call_loop, turn_scope
from agents.types import Agent


def _make_response(
    content: str | None = None,
    thinking: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
) -> ChatResponse:
    tc_list = None
    if tool_calls:
        tc_list = [
            ToolCall(function=ToolCallFunction(name=tc["name"], arguments=tc.get("arguments", {})))
            for tc in tool_calls
        ]
    return ChatResponse(
        message=ChatMessage(content=content, thinking=thinking, tool_calls=tc_list),
        usage=TokenUsage(),
    )


class _ProviderScript:
    """Scripted fake provider that returns queued responses."""

    def __init__(self, responses: list[ChatResponse]):
        self._responses: list[ChatResponse] = list(responses)

    async def chat(self, **_: Any) -> ChatResponse:
        if not self._responses:
            return _make_response(content="done")
        return self._responses.pop(0)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_loop_emits_model_and_tool_call_events(monkeypatch):
    # Arrange: scripted responses -> first triggers a tool call, then finishes
    resp1 = _make_response(
        content="partial",
        thinking="t",
        tool_calls=[{"name": "echo_tool", "arguments": {"x": 1}}],
    )
    resp2 = _make_response(content="done")

    import sdk.loop._tool_loop as mod

    # Patch provider used by the module under test
    monkeypatch.setattr(mod, "get_provider", lambda: _ProviderScript([resp1, resp2]))

    # Minimal tool implementation that will be found by name
    def echo_tool(x: int) -> dict[str, int]:  # noqa: D401 - simple dummy
        return {"x": x}

    # Capture emitted events via the turn_scope
    captured: List[AssistantResponse] = []

    async def _handler(evt: AssistantResponse) -> None:
        captured.append(evt)

    history = ConversationHistory([{"role": "system", "content": "ctx"}])

    # Act: run the tool loop inside a turn scope; drain is automatic on exit
    agent = Agent(
        name="Test Agent",
        description="desc",
        instruction="ctx",
        model="dummy",
        options={},
        tools=[echo_tool],
    )

    async with turn_scope(handler=_handler):
        async for _content, _thinking in run_tool_call_loop(
            history,
            agent=agent,
        ):
            pass

    # Assert: at least two events: one model output and one tool_call
    assert any(e.content == "partial" and e.thinking == "t" for e in captured)
    tool_events = [e.event for e in captured if e.event is not None]
    assert any(
        isinstance(ev, ToolCallPayload) and ev.type == "tool_call" and ev.name == "echo_tool"
        for ev in tool_events
    )
    # Ensure order: model event occurs before tool_call for the same cycle
    first_model_idx = next(i for i, e in enumerate(captured) if e.content == "partial")
    first_tool_idx = next(i for i, e in enumerate(captured) if e.event is not None)
    assert first_model_idx <= first_tool_idx
    # Verify context metadata: tool loop runs in root context (depth 0) when invoked directly
    assert all(e.depth == 0 for e in captured)
