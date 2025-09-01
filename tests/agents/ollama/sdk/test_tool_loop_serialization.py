"""Tests for tool result serialization in run_tool_call_loop.

These tests mock the chat client to emit tool_calls and verify that tool
results are serialized into tool messages as JSON with either a "result"
payload (Pydantic/dicts converted via _to_serializable) or an "error" payload
when tools raise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from agents.ollama.sdk.tool_loop import run_tool_call_loop
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
            "start_line": 12,
            "end_line": 12,
            "replacement": "  box-shadow: 0 2px 10px rgba(0, 0, 0, 10%);\n",
        },
    ))
    resp1 = _Resp(_Message(content=None, thinking=None, tool_calls=[tc]))
    # Second response terminates the loop
    resp2 = _Resp(_Message(content="done", thinking=None, tool_calls=[]))

    # Patch the AsyncClient used in the module
    import agents.ollama.sdk.tool_loop as mod

    monkeypatch.setattr(mod, "AsyncClient", lambda: _ClientScript([resp1, resp2]))

    # Provide tools: a sync function named apply_text_patch that returns a Pydantic model
    def apply_text_patch(path: str, start_line: int, end_line: int, replacement: str) -> ApplyPatchResult:
        return ApplyPatchResult(
            success=True,
            file_path=path,
            diff="--- webos/css/style.css (before)\n+++ webos/css/style.css (after)\n@@ -1,1 +1,1 @@\n-old\n+new\n",
            error=None,
        )

    messages: list[dict[str, Any]] = [{"role": "system", "content": "x"}]
    # Drain the generator
    async for _content, _thinking in run_tool_call_loop(messages, tools=[apply_text_patch], model="dummy"):
        pass

    # Verify the last tool message is the tool serialization (final message may be assistant content)
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
    assert isinstance(result["diff"], str)
    assert result["diff"].startswith("--- webos/css/style.css (before)\n+++ webos/css/style.css (after)\n")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_serialization_apply_text_patch_invalid_range(monkeypatch):
    """Failure result still appears under result key with error populated."""

    tc = _ToolCall(_Func(
        name="apply_text_patch",
        arguments={
            "path": "webos/css/style.css",
            "start_line": 45,
            "end_line": 45,
            "replacement": "  box-shadow: 0 4px 15px rgba(0, 0, 0, 20%);\n}",
        },
    ))
    resp1 = _Resp(_Message(content=None, thinking=None, tool_calls=[tc]))
    resp2 = _Resp(_Message(content="done", thinking=None, tool_calls=[]))

    import agents.ollama.sdk.tool_loop as mod

    monkeypatch.setattr(mod, "AsyncClient", lambda: _ClientScript([resp1, resp2]))

    def apply_text_patch(path: str, start_line: int, end_line: int, replacement: str) -> ApplyPatchResult:
        return ApplyPatchResult(success=False, file_path=path, diff=None, error="Invalid line range")

    messages: list[dict[str, Any]] = [{"role": "system", "content": "x"}]
    async for _content, _thinking in run_tool_call_loop(messages, tools=[apply_text_patch], model="dummy"):
        pass

    tool_msg = next(msg for msg in reversed(messages) if msg.get("role") == "tool")
    payload = json.loads(tool_msg["content"])
    assert "result" in payload
    result = payload["result"]
    assert result["success"] is False
    assert result["error"] == "Invalid line range"
    assert result["diff"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_serialization_tool_exception_as_error(monkeypatch):
    """Exceptions in tool execution serialize as {"error": str(exc)} at top level."""

    tc = _ToolCall(_Func(name="explode", arguments={"x": 1}))
    resp1 = _Resp(_Message(content=None, thinking=None, tool_calls=[tc]))
    resp2 = _Resp(_Message(content="done", thinking=None, tool_calls=[]))

    import agents.ollama.sdk.tool_loop as mod

    monkeypatch.setattr(mod, "AsyncClient", lambda: _ClientScript([resp1, resp2]))

    def explode(x: int) -> str:
        raise RuntimeError("boom")

    messages: list[dict[str, Any]] = [{"role": "system", "content": "x"}]
    async for _content, _thinking in run_tool_call_loop(messages, tools=[explode], model="dummy"):
        pass

    tool_msg = next(msg for msg in reversed(messages) if msg.get("role") == "tool")
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

    monkeypatch.setattr(mod, "AsyncClient", lambda: _ClientScript([resp1, resp2]))

    async def run_bash_cmd(cmd: str) -> dict[str, Any]:
        return {"stdout": "hi\n", "stderr": None, "exit_code": 0}

    messages: list[dict[str, Any]] = [{"role": "system", "content": "x"}]
    async for _content, _thinking in run_tool_call_loop(messages, tools=[run_bash_cmd], model="dummy"):
        pass

    tool_msg = next(msg for msg in reversed(messages) if msg.get("role") == "tool")
    payload = json.loads(tool_msg["content"])
    assert "result" in payload
    assert payload["result"] == {"stdout": "hi\n", "stderr": None, "exit_code": 0}
