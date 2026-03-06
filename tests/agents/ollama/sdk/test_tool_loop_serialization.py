"""Tests for tool result serialization and history behaviour in run_tool_call_loop.

These tests mock the chat client to emit tool_calls and verify that tool
results are serialized into tool messages as JSON with either a "result"
payload (Pydantic/dicts converted via _normalize_tool_result) or an "error" payload
when tools raise.

Additional tests verify the ``persist_thinking`` flag on ``Agent`` controls
whether thinking content is retained in the conversation history while still
being emitted to the UI via events.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from agents.ollama.sdk.context import ConversationHistory
from agents.ollama.sdk.tool_loop import run_tool_call_loop
from agents.types import Agent
from tools.virtual_computer.models import ApplyPatchResult


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
        self._responses = list(responses)

    async def chat(self, **_: Any) -> _Resp:  # noqa: D401 - simple fake
        if not self._responses:
            # Avoid infinite loops if over-consumed
            return _Resp(_Message(content="done", thinking=None, tool_calls=[]))
        return self._responses.pop(0)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_serialization_apply_text_patch_success(monkeypatch):
    """Success case: ApplyPatchResult is serialized under result with full fields."""

    # First response triggers a tool call
    tc = _ToolCall(_Func(
        name="apply_text_patch",
        arguments={
            "path": "webos/css/style.css",
            "old_text": "  box-shadow: 0 2px 10px rgba(0,0,0,10%);",
            "new_text": "  box-shadow: 0 2px 10px rgba(0, 0, 0, 10%);",
        },
    ))
    resp1 = _Resp(_Message(content=None, thinking=None, tool_calls=[tc]))
    # Second response terminates the loop
    resp2 = _Resp(_Message(content="done", thinking=None, tool_calls=[]))

    # Patch the AsyncClient used in the module
    import agents.ollama.sdk.tool_loop as mod

    # Accept *args, **kwargs so keyword-only params like host won't break
    monkeypatch.setattr(mod, "AsyncClient", lambda *_, **__: _ClientScript([resp1, resp2]))

    # Provide tools: a sync function named apply_text_patch that returns a Pydantic model
    def apply_text_patch(path: str, old_text: str, new_text: str) -> ApplyPatchResult:
        return ApplyPatchResult(
            success=True,
            file_path=path,
        )

    history = ConversationHistory([{"role": "system", "content": "x"}])
    agent = Agent(name="Test", description="d", instruction="x", model="dummy", options={}, tools=[apply_text_patch])
    # Drain the generator
    async for _content, _thinking in run_tool_call_loop(history, agent=agent):
        pass

    # Verify the last tool message is the tool serialization (final message may be assistant content)
    messages = history.messages
    tool_msg = next(msg for msg in reversed(messages) if msg.get("role") == "tool")
    assert tool_msg["role"] == "tool"
    assert tool_msg["tool_name"] == "apply_text_patch"
    # Content is JSON string
    payload = json.loads(tool_msg["content"])
    assert "result" in payload and "error" not in payload
    result = payload["result"]
    assert result["success"] is True
    assert result["file_path"] == "webos/css/style.css"
    assert result["error"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_serialization_apply_text_patch_invalid_range(monkeypatch):
    """Failure result still appears under result key with error populated."""

    tc = _ToolCall(_Func(
        name="apply_text_patch",
        arguments={
            "path": "webos/css/style.css",
            "old_text": "nonexistent text",
            "new_text": "  box-shadow: 0 4px 15px rgba(0, 0, 0, 20%);\n}",
        },
    ))
    resp1 = _Resp(_Message(content=None, thinking=None, tool_calls=[tc]))
    resp2 = _Resp(_Message(content="done", thinking=None, tool_calls=[]))

    import agents.ollama.sdk.tool_loop as mod

    monkeypatch.setattr(mod, "AsyncClient", lambda *_, **__: _ClientScript([resp1, resp2]))

    def apply_text_patch(path: str, old_text: str, new_text: str) -> ApplyPatchResult:
        return ApplyPatchResult(success=False, file_path=path, error="No match found")

    history = ConversationHistory([{"role": "system", "content": "x"}])
    agent = Agent(name="Test", description="d", instruction="x", model="dummy", options={}, tools=[apply_text_patch])
    async for _content, _thinking in run_tool_call_loop(history, agent=agent):
        pass

    tool_msg = next(msg for msg in reversed(history.messages) if msg.get("role") == "tool")
    payload = json.loads(tool_msg["content"])
    assert "result" in payload
    result = payload["result"]
    assert result["success"] is False
    assert result["error"] == "No match found"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_serialization_tool_exception_as_error(monkeypatch):
    """Exceptions in tool execution serialize as {"error": str(exc)} at top level."""

    tc = _ToolCall(_Func(name="explode", arguments={"x": 1}))
    resp1 = _Resp(_Message(content=None, thinking=None, tool_calls=[tc]))
    resp2 = _Resp(_Message(content="done", thinking=None, tool_calls=[]))

    import agents.ollama.sdk.tool_loop as mod

    monkeypatch.setattr(mod, "AsyncClient", lambda *_, **__: _ClientScript([resp1, resp2]))

    def explode(x: int) -> str:
        raise RuntimeError("boom")

    history = ConversationHistory([{"role": "system", "content": "x"}])
    agent = Agent(name="Test", description="d", instruction="x", model="dummy", options={}, tools=[explode])
    async for _content, _thinking in run_tool_call_loop(history, agent=agent):
        pass

    tool_msg = next(msg for msg in reversed(history.messages) if msg.get("role") == "tool")
    payload = json.loads(tool_msg["content"])
    assert "error" in payload and "result" not in payload
    assert "boom" in payload["error"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_serialization_async_tool_returns_dict(monkeypatch):
    """Async tool returning a dict should serialize under result without extra conversion."""

    tc = _ToolCall(_Func(name="run_bash_cmd", arguments={"cmd": "echo hi"}))
    resp1 = _Resp(_Message(content=None, thinking=None, tool_calls=[tc]))
    resp2 = _Resp(_Message(content="done", thinking=None, tool_calls=[]))

    import agents.ollama.sdk.tool_loop as mod

    monkeypatch.setattr(mod, "AsyncClient", lambda *_, **__: _ClientScript([resp1, resp2]))

    async def run_bash_cmd(cmd: str) -> dict[str, Any]:
        return {"stdout": "hi\n", "stderr": None, "exit_code": 0}

    history = ConversationHistory([{"role": "system", "content": "x"}])
    agent = Agent(name="Test", description="d", instruction="x", model="dummy", options={}, tools=[run_bash_cmd])
    async for _content, _thinking in run_tool_call_loop(history, agent=agent):
        pass

    tool_msg = next(msg for msg in reversed(history.messages) if msg.get("role") == "tool")
    payload = json.loads(tool_msg["content"])
    assert "result" in payload
    assert payload["result"] == {"stdout": "hi\n", "stderr": None, "exit_code": 0}


# ── persist_thinking tests ──────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_thinking_true_stores_thinking_in_history(monkeypatch):
    """When persist_thinking=True, thinking is stored in the assistant message."""
    resp = _Resp(_Message(content="hello", thinking="deep thought", tool_calls=[]))

    import agents.ollama.sdk.tool_loop as mod

    monkeypatch.setattr(mod, "AsyncClient", lambda *_, **__: _ClientScript([resp]))

    history = ConversationHistory([{"role": "system", "content": "x"}])
    agent = Agent(
        name="Test", description="d", instruction="x",
        model="dummy", options={}, tools=[],
        persist_thinking=True,
    )
    async for _content, _thinking in run_tool_call_loop(history, agent=agent):
        pass

    assistant_msg = next(m for m in history.messages if m["role"] == "assistant")
    assert assistant_msg["thinking"] == "deep thought"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_thinking_false_excludes_thinking_from_history(monkeypatch):
    """When persist_thinking=False, thinking is None in history but still emitted."""
    resp = _Resp(_Message(content="hello", thinking="deep thought", tool_calls=[]))

    import agents.ollama.sdk.tool_loop as mod

    monkeypatch.setattr(mod, "AsyncClient", lambda *_, **__: _ClientScript([resp]))

    # Capture events to verify thinking is still emitted
    emitted_events = []
    original_publish = mod.publish_event

    def _capture_publish(event):
        emitted_events.append(event)
        return original_publish(event)

    monkeypatch.setattr(mod, "publish_event", _capture_publish)

    history = ConversationHistory([{"role": "system", "content": "x"}])
    agent = Agent(
        name="Test", description="d", instruction="x",
        model="dummy", options={}, tools=[],
        persist_thinking=False,
    )
    yielded_thinking = []
    async for _content, thinking in run_tool_call_loop(history, agent=agent):
        yielded_thinking.append(thinking)

    # History should NOT contain thinking
    assistant_msg = next(m for m in history.messages if m["role"] == "assistant")
    assert assistant_msg["thinking"] is None

    # But thinking should still be yielded to the caller
    assert "deep thought" in yielded_thinking

    # And the AssistantResponse event should contain thinking
    content_events = [e for e in emitted_events if hasattr(e, "thinking") and e.thinking]
    assert any(e.thinking == "deep thought" for e in content_events)
