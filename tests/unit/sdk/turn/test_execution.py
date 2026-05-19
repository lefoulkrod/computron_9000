"""Tests for the turn execution engine (sdk.turn._execution).

Covers the full run_turn loop: provider calls, tool execution, hook
invocation order, history mutation, and stop/error propagation.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.types import Agent
from sdk.context import ConversationHistory
from sdk.providers._models import (
    ChatDelta,
    ChatMessage,
    ChatResponse,
    ProviderError,
    TokenUsage,
    ToolCall,
    ToolCallFunction,
)
from sdk.skills.agent_state import AgentState, _active_agent_state
from sdk.turn._execution import ToolLoopError, run_turn
from sdk.turn._turn import StopRequestedError

_MOD = "sdk.turn._execution"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(**overrides: Any) -> Agent:
    defaults = {
        "name": "test-agent",
        "description": "test",
        "instruction": "You are a test agent.",
        "provider": "ollama",
        "model": "test-model",
        "options": {},
        "tools": [],
        "think": False,
        "max_iterations": 0,
    }
    defaults.update(overrides)
    return Agent(**defaults)


async def _dummy_tool(x: str) -> str:
    """A simple tool that echoes its argument."""
    return f"result:{x}"


def _text_response(content: str, *, thinking: str | None = None) -> ChatResponse:
    """A plain text response with no tool calls."""
    return ChatResponse(
        message=ChatMessage(content=content, thinking=thinking),
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
    )


def _tool_call_response(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    call_id: str = "call_1",
    content: str | None = None,
) -> ChatResponse:
    """A response requesting a single tool call."""
    return ChatResponse(
        message=ChatMessage(
            content=content,
            tool_calls=[ToolCall(id=call_id, function=ToolCallFunction(name=tool_name, arguments=arguments))],
        ),
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
    )


class FakeProvider:
    """Mock provider that yields a sequence of responses.

    Each entry in *turns* is either a ChatResponse (non-streaming path) or
    a list of ChatDelta|ChatResponse (streaming path).
    """

    def __init__(self, turns: list[ChatResponse | list[ChatDelta | ChatResponse]]) -> None:
        self._turns = list(turns)
        self._call_count = 0

    async def chat_stream(self, **kwargs: Any) -> AsyncGenerator[ChatDelta | ChatResponse, None]:
        turn = self._turns[self._call_count]
        self._call_count += 1
        if isinstance(turn, list):
            for item in turn:
                yield item
        else:
            yield turn

    async def chat(self, **kwargs: Any) -> ChatResponse:
        turn = self._turns[self._call_count]
        self._call_count += 1
        if isinstance(turn, list):
            # Return the ChatResponse from the list
            return next(item for item in turn if isinstance(item, ChatResponse))
        return turn


class RecordingHook:
    """Hook that records every call for assertion."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def on_turn_start(self, agent_name: str) -> None:
        self.calls.append(("on_turn_start", (agent_name,)))

    async def before_model(self, history: Any, iteration: int, agent_name: str) -> None:
        self.calls.append(("before_model", (iteration, agent_name)))

    async def after_model(self, response: ChatResponse, history: Any, iteration: int, agent_name: str) -> ChatResponse:
        self.calls.append(("after_model", (iteration, agent_name)))
        return response

    def before_tool(self, tool_name: str, tool_arguments: dict[str, Any]) -> str | None:
        self.calls.append(("before_tool", (tool_name, tool_arguments)))
        return None

    def after_tool(self, tool_name: str, tool_arguments: dict[str, Any], tool_result: str) -> str:
        self.calls.append(("after_tool", (tool_name, tool_result)))
        return tool_result

    def on_turn_end(self, final_content: str | None, agent_name: str) -> None:
        self.calls.append(("on_turn_end", (final_content, agent_name)))

    @property
    def phase_names(self) -> list[str]:
        return [name for name, _ in self.calls]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_parallel_config():
    """Disable parallel tool execution by default."""
    cfg = MagicMock()
    cfg.enabled = False
    cfg.max_concurrent = 4
    with patch(f"{_MOD}._get_parallel_config", return_value=cfg):
        yield cfg


@pytest.fixture(autouse=True)
def _patch_publish_event():
    """Stub event publishing so tests don't need a live dispatcher."""
    with patch(f"{_MOD}.publish_event") as mock:
        yield mock


@pytest.fixture(autouse=True)
def _patch_agent_name():
    with patch(f"{_MOD}.get_current_agent_name", return_value="test-agent"):
        yield


def _activate_agent_state(tools: list[Callable[..., Any]]):
    """Set up the AgentState context var with the given tools."""
    state = AgentState(base_tools=tools)
    return _active_agent_state.set(state)


@pytest.fixture(autouse=True)
def _agent_state():
    """Provide a default AgentState with _dummy_tool."""
    token = _activate_agent_state([_dummy_tool])
    yield
    _active_agent_state.reset(token)


# ---------------------------------------------------------------------------
# Tests: happy path
# ---------------------------------------------------------------------------

async def test_simple_text_response() -> None:
    """Provider returns text with no tool calls — single iteration."""
    provider = FakeProvider([_text_response("Hello!")])
    history = ConversationHistory([{"role": "user", "content": "Hi"}])

    with patch(f"{_MOD}.get_provider", return_value=provider):
        result = await run_turn(history, _make_agent())

    assert result == "Hello!"
    assert len(history) == 2
    assert history.messages[-1]["role"] == "assistant"
    assert history.messages[-1]["content"] == "Hello!"


async def test_tool_call_then_final_response() -> None:
    """Provider requests a tool call, gets the result, then responds with text."""
    provider = FakeProvider([
        _tool_call_response("_dummy_tool", {"x": "ping"}),
        _text_response("Got it: result:ping"),
    ])
    history = ConversationHistory([{"role": "user", "content": "call the tool"}])

    with patch(f"{_MOD}.get_provider", return_value=provider):
        result = await run_turn(history, _make_agent())

    assert result == "Got it: result:ping"
    # History: user, assistant (tool call), tool result, assistant (final)
    assert len(history) == 4
    assert history.messages[1]["role"] == "assistant"
    assert history.messages[1]["tool_calls"] is not None
    assert history.messages[2]["role"] == "tool"
    assert history.messages[2]["content"] == "result:ping"
    assert history.messages[3]["role"] == "assistant"
    assert history.messages[3]["content"] == "Got it: result:ping"


async def test_multiple_tool_calls_sequential() -> None:
    """Two tool calls in a single response, executed sequentially."""
    response_with_two_tools = ChatResponse(
        message=ChatMessage(
            content=None,
            tool_calls=[
                ToolCall(id="c1", function=ToolCallFunction(name="_dummy_tool", arguments={"x": "a"})),
                ToolCall(id="c2", function=ToolCallFunction(name="_dummy_tool", arguments={"x": "b"})),
            ],
        ),
        usage=TokenUsage(),
    )
    provider = FakeProvider([response_with_two_tools, _text_response("done")])
    history = ConversationHistory([{"role": "user", "content": "go"}])

    with patch(f"{_MOD}.get_provider", return_value=provider):
        result = await run_turn(history, _make_agent())

    assert result == "done"
    tool_msgs = [m for m in history.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 2
    assert tool_msgs[0]["content"] == "result:a"
    assert tool_msgs[1]["content"] == "result:b"


async def test_streaming_deltas_published(_patch_publish_event: MagicMock) -> None:
    """Streaming deltas are published as events before the final response."""
    streamed_turn: list[ChatDelta | ChatResponse] = [
        ChatDelta(content="Hel"),
        ChatDelta(content="lo!"),
        _text_response("Hello!"),
    ]
    provider = FakeProvider([streamed_turn])
    history = ConversationHistory([{"role": "user", "content": "Hi"}])

    with patch(f"{_MOD}.get_provider", return_value=provider):
        result = await run_turn(history, _make_agent())

    assert result == "Hello!"
    # Two delta events + one turn_end event
    delta_calls = [
        c for c in _patch_publish_event.call_args_list
        if hasattr(c.args[0].payload, "delta") and c.args[0].payload.delta is True
    ]
    assert len(delta_calls) == 2


# ---------------------------------------------------------------------------
# Tests: hook invocation
# ---------------------------------------------------------------------------

async def test_hooks_fire_in_order_text_only() -> None:
    """For a text-only response, hooks fire: start, before, after, end."""
    provider = FakeProvider([_text_response("ok")])
    history = ConversationHistory([{"role": "user", "content": "hi"}])
    hook = RecordingHook()

    with patch(f"{_MOD}.get_provider", return_value=provider):
        await run_turn(history, _make_agent(), hooks=[hook])

    assert hook.phase_names == [
        "on_turn_start",
        "before_model",
        "after_model",
        "on_turn_end",
    ]


async def test_hooks_fire_in_order_with_tool_call() -> None:
    """Full cycle: start, before, after, before_tool, after_tool, before, after, end."""
    provider = FakeProvider([
        _tool_call_response("_dummy_tool", {"x": "v"}),
        _text_response("final"),
    ])
    history = ConversationHistory([{"role": "user", "content": "go"}])
    hook = RecordingHook()

    with patch(f"{_MOD}.get_provider", return_value=provider):
        await run_turn(history, _make_agent(), hooks=[hook])

    assert hook.phase_names == [
        "on_turn_start",
        # iteration 1: model returns tool call
        "before_model",
        "after_model",
        "before_tool",
        "after_tool",
        # iteration 2: model returns final text
        "before_model",
        "after_model",
        "on_turn_end",
    ]


async def test_before_tool_intercept_skips_execution() -> None:
    """A before_tool hook returning a string intercepts the real tool."""

    class InterceptHook:
        def before_tool(self, name: str, args: dict) -> str | None:
            return "intercepted-result"

    provider = FakeProvider([
        _tool_call_response("_dummy_tool", {"x": "ignored"}),
        _text_response("done"),
    ])
    history = ConversationHistory([{"role": "user", "content": "go"}])

    with patch(f"{_MOD}.get_provider", return_value=provider):
        await run_turn(history, _make_agent(), hooks=[InterceptHook()])

    tool_msg = next(m for m in history.messages if m["role"] == "tool")
    assert tool_msg["content"] == "intercepted-result"


async def test_after_tool_transforms_result() -> None:
    """An after_tool hook can rewrite the tool result."""

    class TransformHook:
        def after_tool(self, name: str, args: dict, result: str) -> str:
            return result.upper()

    provider = FakeProvider([
        _tool_call_response("_dummy_tool", {"x": "hello"}),
        _text_response("done"),
    ])
    history = ConversationHistory([{"role": "user", "content": "go"}])

    with patch(f"{_MOD}.get_provider", return_value=provider):
        await run_turn(history, _make_agent(), hooks=[TransformHook()])

    tool_msg = next(m for m in history.messages if m["role"] == "tool")
    assert tool_msg["content"] == "RESULT:HELLO"


async def test_after_model_can_rewrite_response() -> None:
    """An after_model hook can rewrite the ChatResponse."""

    class RewriteHook:
        async def after_model(self, response: ChatResponse, history: Any, iteration: int, agent_name: str) -> ChatResponse:
            return ChatResponse(
                message=ChatMessage(content="rewritten"),
                usage=response.usage,
            )

    provider = FakeProvider([_text_response("original")])
    history = ConversationHistory([{"role": "user", "content": "hi"}])

    with patch(f"{_MOD}.get_provider", return_value=provider):
        result = await run_turn(history, _make_agent(), hooks=[RewriteHook()])

    assert result == "rewritten"
    assert history.messages[-1]["content"] == "rewritten"


# ---------------------------------------------------------------------------
# Tests: on_turn_end always fires
# ---------------------------------------------------------------------------

async def test_on_turn_end_fires_on_success() -> None:
    provider = FakeProvider([_text_response("ok")])
    history = ConversationHistory([{"role": "user", "content": "hi"}])
    hook = RecordingHook()

    with patch(f"{_MOD}.get_provider", return_value=provider):
        await run_turn(history, _make_agent(), hooks=[hook])

    end_calls = [c for c in hook.calls if c[0] == "on_turn_end"]
    assert len(end_calls) == 1
    assert end_calls[0][1] == ("ok", "test-agent")


async def test_on_turn_end_fires_on_stop() -> None:
    """on_turn_end runs even when the turn is stopped."""

    class StopOnBeforeModel:
        async def before_model(self, history: Any, iteration: int, agent_name: str) -> None:
            raise StopRequestedError()

    hook = RecordingHook()
    provider = FakeProvider([_text_response("unreachable")])
    history = ConversationHistory([{"role": "user", "content": "hi"}])

    with patch(f"{_MOD}.get_provider", return_value=provider):
        with pytest.raises(StopRequestedError):
            await run_turn(history, _make_agent(), hooks=[StopOnBeforeModel(), hook])

    assert "on_turn_end" in hook.phase_names


async def test_on_turn_end_fires_on_error() -> None:
    """on_turn_end runs even when the turn hits an unexpected error."""

    class BrokenBeforeModel:
        async def before_model(self, history: Any, iteration: int, agent_name: str) -> None:
            raise RuntimeError("boom")

    hook = RecordingHook()
    provider = FakeProvider([_text_response("unreachable")])
    history = ConversationHistory([{"role": "user", "content": "hi"}])

    with patch(f"{_MOD}.get_provider", return_value=provider):
        with pytest.raises(ToolLoopError):
            await run_turn(history, _make_agent(), hooks=[BrokenBeforeModel(), hook])

    assert "on_turn_end" in hook.phase_names


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------

async def test_stop_requested_propagates() -> None:
    """StopRequestedError during tool execution surfaces to the caller."""

    async def _stopping_tool(x: str) -> str:
        raise StopRequestedError()

    token = _activate_agent_state([_stopping_tool])
    try:
        provider = FakeProvider([
            _tool_call_response("_stopping_tool", {"x": "go"}),
        ])
        history = ConversationHistory([{"role": "user", "content": "go"}])

        with patch(f"{_MOD}.get_provider", return_value=provider):
            with pytest.raises(StopRequestedError):
                await run_turn(history, _make_agent())
    finally:
        _active_agent_state.reset(token)


async def test_tool_error_wrapped_in_tool_loop_error() -> None:
    """An unexpected error in a tool becomes a ToolLoopError."""

    async def _broken_tool(x: str) -> str:
        raise ValueError("tool broke")

    token = _activate_agent_state([_broken_tool])
    try:
        provider = FakeProvider([
            _tool_call_response("_broken_tool", {"x": "go"}),
        ])
        history = ConversationHistory([{"role": "user", "content": "go"}])

        with patch(f"{_MOD}.get_provider", return_value=provider):
            with pytest.raises(ToolLoopError):
                await run_turn(history, _make_agent())
    finally:
        _active_agent_state.reset(token)


async def test_non_retryable_provider_error_raises_immediately() -> None:
    """A non-retryable ProviderError is not retried."""

    class FailingProvider:
        async def chat_stream(self, **kw: Any) -> AsyncGenerator[ChatDelta | ChatResponse, None]:
            raise ProviderError("bad request", retryable=False)
            yield  # make it a generator

    history = ConversationHistory([{"role": "user", "content": "hi"}])

    with patch(f"{_MOD}.get_provider", return_value=FailingProvider()):
        with pytest.raises(ToolLoopError):
            await run_turn(history, _make_agent())


async def test_no_agent_state_raises() -> None:
    """run_turn outside an agent_span raises ToolLoopError."""
    _active_agent_state.set(None)
    provider = FakeProvider([_text_response("x")])
    history = ConversationHistory([{"role": "user", "content": "hi"}])

    with patch(f"{_MOD}.get_provider", return_value=provider):
        with pytest.raises(ToolLoopError, match="agent_span"):
            await run_turn(history, _make_agent())


# ---------------------------------------------------------------------------
# Tests: history mutation
# ---------------------------------------------------------------------------

async def test_assistant_message_includes_agent_name() -> None:
    provider = FakeProvider([_text_response("hi")])
    history = ConversationHistory([{"role": "user", "content": "hello"}])

    with patch(f"{_MOD}.get_provider", return_value=provider):
        await run_turn(history, _make_agent())

    assert history.messages[-1]["agent_name"] == "test-agent"


async def test_tool_calls_serialized_as_dicts() -> None:
    """Tool calls in history are plain dicts, not Pydantic models."""
    provider = FakeProvider([
        _tool_call_response("_dummy_tool", {"x": "v"}),
        _text_response("done"),
    ])
    history = ConversationHistory([{"role": "user", "content": "go"}])

    with patch(f"{_MOD}.get_provider", return_value=provider):
        await run_turn(history, _make_agent())

    assistant_msg = history.messages[1]
    tc = assistant_msg["tool_calls"][0]
    assert isinstance(tc, dict)
    assert tc["function"]["name"] == "_dummy_tool"


async def test_tool_result_has_call_id_and_name() -> None:
    provider = FakeProvider([
        _tool_call_response("_dummy_tool", {"x": "v"}, call_id="call_abc"),
        _text_response("done"),
    ])
    history = ConversationHistory([{"role": "user", "content": "go"}])

    with patch(f"{_MOD}.get_provider", return_value=provider):
        await run_turn(history, _make_agent())

    tool_msg = next(m for m in history.messages if m["role"] == "tool")
    assert tool_msg["tool_call_id"] == "call_abc"
    assert tool_msg["tool_name"] == "_dummy_tool"


async def test_thinking_preserved_in_history() -> None:
    """Model thinking content is stored in the assistant message."""
    provider = FakeProvider([_text_response("answer", thinking="let me think...")])
    history = ConversationHistory([{"role": "user", "content": "think about it"}])

    with patch(f"{_MOD}.get_provider", return_value=provider):
        await run_turn(history, _make_agent())

    assert history.messages[-1]["thinking"] == "let me think..."


# ---------------------------------------------------------------------------
# Tests: parallel tool execution
# ---------------------------------------------------------------------------

async def test_parallel_tool_calls(_patch_parallel_config: MagicMock) -> None:
    """With parallel enabled, multiple tool calls run concurrently."""
    _patch_parallel_config.enabled = True
    _patch_parallel_config.max_concurrent = 4

    response_with_two_tools = ChatResponse(
        message=ChatMessage(
            content=None,
            tool_calls=[
                ToolCall(id="c1", function=ToolCallFunction(name="_dummy_tool", arguments={"x": "a"})),
                ToolCall(id="c2", function=ToolCallFunction(name="_dummy_tool", arguments={"x": "b"})),
            ],
        ),
        usage=TokenUsage(),
    )
    provider = FakeProvider([response_with_two_tools, _text_response("done")])
    history = ConversationHistory([{"role": "user", "content": "go"}])

    with patch(f"{_MOD}.get_provider", return_value=provider):
        result = await run_turn(history, _make_agent())

    assert result == "done"
    tool_msgs = [m for m in history.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 2
    results = {m["content"] for m in tool_msgs}
    assert results == {"result:a", "result:b"}


async def test_parallel_tool_failure_recorded_as_result(_patch_parallel_config: MagicMock) -> None:
    """A failing tool in parallel mode gets its error caught by _execute_tool_call
    and recorded as a normal tool result string, not an exception."""
    _patch_parallel_config.enabled = True

    async def _failing_tool(x: str) -> str:
        raise ValueError("nope")

    token = _activate_agent_state([_dummy_tool, _failing_tool])
    try:
        response = ChatResponse(
            message=ChatMessage(
                content=None,
                tool_calls=[
                    ToolCall(id="c1", function=ToolCallFunction(name="_dummy_tool", arguments={"x": "ok"})),
                    ToolCall(id="c2", function=ToolCallFunction(name="_failing_tool", arguments={"x": "bad"})),
                ],
            ),
            usage=TokenUsage(),
        )
        provider = FakeProvider([response, _text_response("recovered")])
        history = ConversationHistory([{"role": "user", "content": "go"}])

        with patch(f"{_MOD}.get_provider", return_value=provider):
            result = await run_turn(history, _make_agent())

        assert result == "recovered"
        tool_msgs = [m for m in history.messages if m["role"] == "tool"]
        assert len(tool_msgs) == 2
        error_msg = next(m for m in tool_msgs if m["tool_call_id"] == "c2")
        assert "nope" in error_msg["content"]
    finally:
        _active_agent_state.reset(token)


async def test_parallel_stop_requested_propagates(_patch_parallel_config: MagicMock) -> None:
    """StopRequestedError from a parallel tool halts the turn, not silently recorded."""
    _patch_parallel_config.enabled = True

    async def _stopping_tool(x: str) -> str:
        raise StopRequestedError()

    token = _activate_agent_state([_dummy_tool, _stopping_tool])
    try:
        response = ChatResponse(
            message=ChatMessage(
                content=None,
                tool_calls=[
                    ToolCall(id="c1", function=ToolCallFunction(name="_dummy_tool", arguments={"x": "ok"})),
                    ToolCall(id="c2", function=ToolCallFunction(name="_stopping_tool", arguments={"x": "stop"})),
                ],
            ),
            usage=TokenUsage(),
        )
        provider = FakeProvider([response])
        history = ConversationHistory([{"role": "user", "content": "go"}])

        with patch(f"{_MOD}.get_provider", return_value=provider):
            with pytest.raises(StopRequestedError):
                await run_turn(history, _make_agent())
    finally:
        _active_agent_state.reset(token)
