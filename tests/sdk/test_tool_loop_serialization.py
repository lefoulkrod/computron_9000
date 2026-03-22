"""Tests for tool result serialization and history behaviour in run_turn.

These tests mock the provider to emit tool_calls and verify that tool
results are stored as plain strings in tool messages — Pydantic models are
normalized via _normalize_tool_result and str()-converted, exceptions become
their string representation, and dicts are str()-converted.

Additional tests verify the ``persist_thinking`` flag on ``Agent`` controls
whether thinking content is retained in the conversation history while still
being emitted to the UI via events.
"""

from __future__ import annotations

from typing import Any

import pytest

from sdk.context import ConversationHistory
from sdk.providers._models import ChatMessage, ChatResponse, TokenUsage
from sdk.turn import run_turn
from agents.types import Agent
from tools.virtual_computer.models import ApplyPatchResult


def _make_response(
    content: str | None = None,
    thinking: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
) -> ChatResponse:
    """Build a normalized ChatResponse for testing."""
    from sdk.providers._models import ToolCall, ToolCallFunction

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
        self._responses = list(responses)

    async def chat(self, **_: Any) -> ChatResponse:
        if not self._responses:
            return _make_response(content="done")
        return self._responses.pop(0)

    async def chat_stream(self, **kwargs: Any):
        yield await self.chat(**kwargs)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_serialization_apply_text_patch_success(monkeypatch):
    """Success case: ApplyPatchResult is serialized under result with full fields."""
    resp1 = _make_response(tool_calls=[{
        "name": "apply_text_patch",
        "arguments": {
            "path": "webos/css/style.css",
            "old_text": "  box-shadow: 0 2px 10px rgba(0,0,0,10%);",
            "new_text": "  box-shadow: 0 2px 10px rgba(0, 0, 0, 10%);",
        },
    }])
    resp2 = _make_response(content="done")

    import sdk.turn._execution as mod

    monkeypatch.setattr(mod, "get_provider", lambda: _ProviderScript([resp1, resp2]))

    def apply_text_patch(path: str, old_text: str, new_text: str) -> ApplyPatchResult:
        return ApplyPatchResult(
            success=True,
            file_path=path,
        )

    history = ConversationHistory([{"role": "system", "content": "x"}])
    agent = Agent(name="Test", description="d", instruction="x", model="dummy", options={}, tools=[apply_text_patch])
    await run_turn(history, agent=agent)

    messages = history.messages
    tool_msg = next(msg for msg in reversed(messages) if msg.get("role") == "tool")
    assert tool_msg["role"] == "tool"
    assert tool_msg["tool_name"] == "apply_text_patch"
    content = tool_msg["content"]
    assert isinstance(content, str)
    assert "success" in content
    assert "webos/css/style.css" in content


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_serialization_apply_text_patch_invalid_range(monkeypatch):
    """Failure result still appears under result key with error populated."""
    resp1 = _make_response(tool_calls=[{
        "name": "apply_text_patch",
        "arguments": {
            "path": "webos/css/style.css",
            "old_text": "nonexistent text",
            "new_text": "  box-shadow: 0 4px 15px rgba(0, 0, 0, 20%);\n}",
        },
    }])
    resp2 = _make_response(content="done")

    import sdk.turn._execution as mod

    monkeypatch.setattr(mod, "get_provider", lambda: _ProviderScript([resp1, resp2]))

    def apply_text_patch(path: str, old_text: str, new_text: str) -> ApplyPatchResult:
        return ApplyPatchResult(success=False, file_path=path, error="No match found")

    history = ConversationHistory([{"role": "system", "content": "x"}])
    agent = Agent(name="Test", description="d", instruction="x", model="dummy", options={}, tools=[apply_text_patch])
    await run_turn(history, agent=agent)

    tool_msg = next(msg for msg in reversed(history.messages) if msg.get("role") == "tool")
    content = tool_msg["content"]
    assert isinstance(content, str)
    assert "success" in content
    assert "No match found" in content


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_serialization_tool_exception_as_error(monkeypatch):
    """Exceptions in tool execution serialize as {"error": str(exc)} at top level."""
    resp1 = _make_response(tool_calls=[{"name": "explode", "arguments": {"x": 1}}])
    resp2 = _make_response(content="done")

    import sdk.turn._execution as mod

    monkeypatch.setattr(mod, "get_provider", lambda: _ProviderScript([resp1, resp2]))

    def explode(x: int) -> str:
        raise RuntimeError("boom")

    history = ConversationHistory([{"role": "system", "content": "x"}])
    agent = Agent(name="Test", description="d", instruction="x", model="dummy", options={}, tools=[explode])
    await run_turn(history, agent=agent)

    tool_msg = next(msg for msg in reversed(history.messages) if msg.get("role") == "tool")
    content = tool_msg["content"]
    assert isinstance(content, str)
    assert "boom" in content


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_serialization_async_tool_returns_dict(monkeypatch):
    """Async tool returning a dict should serialize under result without extra conversion."""
    resp1 = _make_response(tool_calls=[{"name": "run_bash_cmd", "arguments": {"cmd": "echo hi"}}])
    resp2 = _make_response(content="done")

    import sdk.turn._execution as mod

    monkeypatch.setattr(mod, "get_provider", lambda: _ProviderScript([resp1, resp2]))

    async def run_bash_cmd(cmd: str) -> dict[str, Any]:
        return {"stdout": "hi\n", "stderr": None, "exit_code": 0}

    history = ConversationHistory([{"role": "system", "content": "x"}])
    agent = Agent(name="Test", description="d", instruction="x", model="dummy", options={}, tools=[run_bash_cmd])
    await run_turn(history, agent=agent)

    tool_msg = next(msg for msg in reversed(history.messages) if msg.get("role") == "tool")
    content = tool_msg["content"]
    assert isinstance(content, str)
    assert "stdout" in content
    assert "hi" in content
    assert "exit_code" in content


# ── persist_thinking tests ──────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_thinking_true_stores_thinking_in_history(monkeypatch):
    """When persist_thinking=True, thinking is stored in the assistant message."""
    resp = _make_response(content="hello", thinking="deep thought")

    import sdk.turn._execution as mod

    monkeypatch.setattr(mod, "get_provider", lambda: _ProviderScript([resp]))

    history = ConversationHistory([{"role": "system", "content": "x"}])
    agent = Agent(
        name="Test", description="d", instruction="x",
        model="dummy", options={}, tools=[],
        persist_thinking=True,
    )
    await run_turn(history, agent=agent)

    assistant_msg = next(m for m in history.messages if m["role"] == "assistant")
    assert assistant_msg["thinking"] == "deep thought"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_thinking_false_excludes_thinking_from_history(monkeypatch):
    """When persist_thinking=False, thinking is None in history but still emitted."""
    resp = _make_response(content="hello", thinking="deep thought")

    import sdk.turn._execution as mod

    monkeypatch.setattr(mod, "get_provider", lambda: _ProviderScript([resp]))

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
    await run_turn(history, agent=agent)

    # History should NOT contain thinking
    assistant_msg = next(m for m in history.messages if m["role"] == "assistant")
    assert assistant_msg["thinking"] is None

    # But thinking should still be emitted via events
    content_events = [e for e in emitted_events if hasattr(e, "thinking") and e.thinking]
    assert any(e.thinking == "deep thought" for e in content_events)
