"""Tests that tool loop publishes AssistantResponse events via the dispatcher.

Covers:
- Emission of content/thinking events after a model response
- Emission of tool_call event before executing a tool
- Preservation of generator contract (still yields content, thinking)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncGenerator, List

import pytest

from agents.ollama.sdk.events import AssistantResponse, ToolCallPayload, event_context
from agents.ollama.sdk.tool_loop import run_tool_call_loop


@dataclass
class _Func:
    name: str
    arguments: dict[str, Any]


@dataclass
class _ToolCall:
    function: _Func


@dataclass
class _Message:
    content: str | None
    thinking: str | None
    tool_calls: list[_ToolCall]


@dataclass
class _Resp:
    message: _Message


class _ClientScript:
    """Scripted fake AsyncClient that returns queued responses."""

    def __init__(self, responses: list[_Resp]):
        self._responses: list[_Resp] = list(responses)

    async def chat(self, **_: Any) -> _Resp:  # noqa: D401 - deterministic fake
        if not self._responses:
            return _Resp(_Message(content="done", thinking=None, tool_calls=[]))
        return self._responses.pop(0)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_loop_emits_model_and_tool_call_events(monkeypatch):
    # Arrange: scripted responses -> first triggers a tool call, then finishes
    tc = _ToolCall(_Func(name="echo_tool", arguments={"x": 1}))
    resp1 = _Resp(_Message(content="partial", thinking="t", tool_calls=[tc]))
    resp2 = _Resp(_Message(content="done", thinking=None, tool_calls=[]))

    import agents.ollama.sdk.tool_loop as mod

    # Patch client used by the module under test
    monkeypatch.setattr(mod, "AsyncClient", lambda *_, **__: _ClientScript([resp1, resp2]))

    # Minimal tool implementation that will be found by name
    def echo_tool(x: int) -> dict[str, int]:  # noqa: D401 - simple dummy
        return {"x": x}

    # Capture emitted events via the event_context
    captured: List[AssistantResponse] = []

    async def _handler(evt: AssistantResponse) -> None:
        captured.append(evt)

    messages: list[dict[str, Any]] = [{"role": "system", "content": "ctx"}]

    # Act: run the tool loop inside an event context
    async with event_context(handler=_handler):
        async for _content, _thinking in run_tool_call_loop(
            messages,
            tools=[echo_tool],
            model="dummy",
        ):
            # Drain the generator without assertions here; assertions happen after
            pass
    # Allow scheduled handler tasks to run before exiting the context.
    # We could expose the underlying dispatcher to call drain() directly,
    # but for now a single loop tick suffices because handlers are trivial.
    await asyncio.sleep(0)

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
