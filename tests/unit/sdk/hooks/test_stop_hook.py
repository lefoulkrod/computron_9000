"""Tests for StopHook."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from sdk.hooks._stop_hook import StopHook
from sdk.turn import StopRequestedError


class _FakeHistory:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def append(self, msg: dict[str, Any]) -> None:
        self.messages.append(msg)


class _FakeResponse:
    """Minimal ChatResponse stand-in for testing."""

    def __init__(self, content: str | None = None, tool_calls: list | None = None) -> None:
        self.message = _FakeMessage(content, tool_calls)


class _FakeMessage:
    def __init__(self, content: str | None = None, tool_calls: list | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls


# ---------------------------------------------------------------------------
# before_model
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_before_model_raises_when_stop_requested() -> None:
    """before_model raises StopRequestedError when the stop event is set."""
    hook = StopHook()
    history = _FakeHistory()
    with patch("sdk.hooks._stop_hook.check_stop", side_effect=StopRequestedError()):
        with pytest.raises(StopRequestedError):
            await hook.before_model(history, 1, "TEST")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_before_model_noop_when_no_stop() -> None:
    """before_model does nothing when no stop has been requested."""
    hook = StopHook()
    history = _FakeHistory()
    with patch("sdk.hooks._stop_hook.check_stop", return_value=None):
        await hook.before_model(history, 1, "TEST")
    assert len(history.messages) == 0


# ---------------------------------------------------------------------------
# after_model — stop requested DURING model call
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_after_model_strips_tool_calls_on_stop() -> None:
    """When stop is requested, tool_calls are stripped so the turn ends cleanly."""
    hook = StopHook()
    history = _FakeHistory()
    response = _FakeResponse(content="Here is the result", tool_calls=["dummy_call"])

    with patch("sdk.hooks._stop_hook.check_stop", side_effect=StopRequestedError()):
        result = await hook.after_model(response, history, 1, "TEST")

    # Tool calls must be stripped
    assert result.message.tool_calls is None
    # Content must be preserved
    assert result.message.content == "Here is the result"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_after_model_appends_nudge_on_stop() -> None:
    """When stop is requested, a nudge is appended to history."""
    hook = StopHook()
    history = _FakeHistory()
    response = _FakeResponse(content="partial work")

    with patch("sdk.hooks._stop_hook.check_stop", side_effect=StopRequestedError()):
        await hook.after_model(response, history, 1, "TEST")

    assert len(history.messages) == 1
    assert "stop" in history.messages[0]["content"].lower()
    assert history.messages[0]["role"] == "user"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_after_model_does_not_raise_on_stop() -> None:
    """after_model must NOT raise StopRequestedError — raising would skip the
    assistant-message append in run_turn, losing the model's response."""
    hook = StopHook()
    history = _FakeHistory()
    response = _FakeResponse(content="final answer", tool_calls=["call_1"])

    with patch("sdk.hooks._stop_hook.check_stop", side_effect=StopRequestedError()):
        # This must NOT raise
        result = await hook.after_model(response, history, 1, "TEST")

    assert result is not None
    assert result.message.content == "final answer"
    assert result.message.tool_calls is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_after_model_preserves_response_without_tool_calls() -> None:
    """When the model returns content without tool_calls and stop is requested,
    the response is still preserved."""
    hook = StopHook()
    history = _FakeHistory()
    response = _FakeResponse(content="all done", tool_calls=None)

    with patch("sdk.hooks._stop_hook.check_stop", side_effect=StopRequestedError()):
        result = await hook.after_model(response, history, 1, "TEST")

    assert result.message.content == "all done"
    assert result.message.tool_calls is None
    assert len(history.messages) == 1  # nudge appended


# ---------------------------------------------------------------------------
# after_model — normal path (no stop)
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_after_model_noop_when_no_stop() -> None:
    """after_model returns the response unchanged when no stop is requested."""
    hook = StopHook()
    history = _FakeHistory()
    response = _FakeResponse(content="ok", tool_calls=["call_1"])

    with patch("sdk.hooks._stop_hook.check_stop", return_value=None):
        result = await hook.after_model(response, history, 1, "TEST")

    assert result is response
    assert result.message.tool_calls == ["call_1"]
    assert len(history.messages) == 0
