"""Tests that tool loop publishes AgentEvent events via the dispatcher.

Covers:
- Emission of content/thinking events after a model response
- Emission of tool_call event before executing a tool
"""

from __future__ import annotations

from typing import Any, List

import pytest

from sdk.context import ConversationHistory
from sdk.events import AgentEvent, ContentPayload, ToolCallPayload, agent_span
from sdk.skills import AgentState
from sdk.providers._models import ChatMessage, ChatResponse, TokenUsage, ToolCall, ToolCallFunction
from sdk.turn import run_turn, turn_scope
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

    async def chat_stream(self, **kwargs: Any):
        yield await self.chat(**kwargs)


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

    import sdk.turn._execution as mod

    # Patch provider used by the module under test
    monkeypatch.setattr(mod, "get_provider", lambda: _ProviderScript([resp1, resp2]))

    # Minimal tool implementation that will be found by name
    def echo_tool(x: int) -> dict[str, int]:  # noqa: D401 - simple dummy
        return {"x": x}

    # Capture emitted events via the turn_scope
    captured: List[AgentEvent] = []

    async def _handler(evt: AgentEvent) -> None:
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
        async with agent_span("Test", agent_state=AgentState(agent.tools)):
            await run_turn(
                history,
                agent=agent,
            )

    # Assert: at least two events: one model output and one tool_call
    assert any(
        isinstance(e.payload, ContentPayload) and e.payload.content == "partial" and e.payload.thinking == "t"
        for e in captured
    )
    tool_events = [e.payload for e in captured if isinstance(e.payload, ToolCallPayload)]
    assert any(
        ev.type == "tool_call" and ev.name == "echo_tool"
        for ev in tool_events
    )
    # Ensure order: model event occurs before tool_call for the same cycle
    first_model_idx = next(
        i for i, e in enumerate(captured)
        if isinstance(e.payload, ContentPayload) and e.payload.content == "partial"
    )
    first_tool_idx = next(
        i for i, e in enumerate(captured) if isinstance(e.payload, ToolCallPayload)
    )
    assert first_model_idx <= first_tool_idx
    # Verify context metadata: tool loop runs in root context (depth 0) when invoked directly
    assert all(e.depth == 0 for e in captured)
