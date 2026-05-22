"""Tests for OpenAIResponsesProvider streaming and normalization."""

import json
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from sdk.providers._models import ChatResponse, ToolCall, ToolCallFunction
from sdk.providers._openai_responses import (
    _build_tool_calls,
    _convert_messages,
    _convert_tools,
    _extract_usage,
    _normalize_response,
)


# ---------------------------------------------------------------------------
# Fake event objects for streaming tests
# ---------------------------------------------------------------------------


@dataclass
class _FakeItem:
    type: str
    id: str = ""
    call_id: str = ""
    name: str = ""


@dataclass
class _FakeEvent:
    type: str
    delta: str = ""
    output_index: int = 0
    item: _FakeItem | None = None
    response: Any = None


@dataclass
class _FakeContentBlock:
    type: str
    text: str = ""


@dataclass
class _FakeOutputItem:
    type: str
    content: list[_FakeContentBlock] = field(default_factory=list)
    name: str = ""
    call_id: str = ""
    arguments: str = ""


@dataclass
class _FakeSummary:
    type: str
    text: str = ""


@dataclass
class _FakeReasoning:
    type: str = "reasoning"
    summary: list[_FakeSummary] = field(default_factory=list)


@dataclass
class _FakeUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    input_tokens_details: Any = None


@dataclass
class _FakeResponse:
    output: list[_FakeOutputItem] = field(default_factory=list)
    status: str = "completed"
    usage: _FakeUsage = field(default_factory=_FakeUsage)


# ---------------------------------------------------------------------------
# _convert_messages
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConvertMessages:
    def test_system_becomes_instructions(self):
        msgs = [{"role": "system", "content": "You are helpful."}]
        instructions, items = _convert_messages(msgs)
        assert instructions == "You are helpful."
        assert items == []

    def test_user_message_passes_through(self):
        msgs = [{"role": "user", "content": "hello"}]
        instructions, items = _convert_messages(msgs)
        assert instructions is None
        assert items == [{"role": "user", "content": "hello"}]

    def test_user_with_images(self):
        msgs = [
            {
                "role": "user",
                "content": "describe this",
                "images": [{"media_type": "image/png", "data": "abc123"}],
            }
        ]
        instructions, items = _convert_messages(msgs)
        assert instructions is None
        assert items[0]["role"] == "user"
        assert isinstance(items[0]["content"], list)
        assert items[0]["content"][0] == {"type": "input_text", "text": "describe this"}
        assert items[0]["content"][1]["type"] == "input_image"

    def test_assistant_with_content(self):
        msgs = [{"role": "assistant", "content": "I'll help."}]
        instructions, items = _convert_messages(msgs)
        assert instructions is None
        assert items[0]["type"] == "message"
        assert items[0]["role"] == "assistant"
        assert items[0]["content"][0]["text"] == "I'll help."

    def test_assistant_with_tool_calls(self):
        msgs = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_abc",
                        "function": {"name": "search", "arguments": {"q": "test"}},
                    }
                ],
            }
        ]
        instructions, items = _convert_messages(msgs)
        assert instructions is None
        assert items[0]["type"] == "function_call"
        assert items[0]["call_id"] == "call_abc"
        assert items[0]["name"] == "search"
        assert json.loads(items[0]["arguments"]) == {"q": "test"}

    def test_tool_result(self):
        msgs = [{"role": "tool", "tool_call_id": "call_1", "content": "result"}]
        instructions, items = _convert_messages(msgs)
        assert instructions is None
        assert items[0]["type"] == "function_call_output"
        assert items[0]["call_id"] == "call_1"
        assert items[0]["output"] == "result"

    def test_tool_result_dict_content(self):
        msgs = [{"role": "tool", "tool_call_id": "call_2", "content": {"k": "v"}}]
        instructions, items = _convert_messages(msgs)
        assert items[0]["output"] == '{"k": "v"}'


# ---------------------------------------------------------------------------
# _build_tool_calls
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildToolCalls:
    def test_valid_arguments(self):
        accum = {0: {"id": "fc_abc", "call_id": "call_abc", "name": "search", "arguments": '{"q": "hello"}'}}
        result = _build_tool_calls(accum)
        assert result is not None
        assert len(result) == 1
        assert result[0].id == "call_abc"
        assert result[0].function.name == "search"
        assert result[0].function.arguments == {"q": "hello"}

    def test_falls_back_to_id_when_call_id_empty(self):
        accum = {0: {"id": "fc_xyz", "call_id": "", "name": "fn", "arguments": "{}"}}
        result = _build_tool_calls(accum)
        assert result is not None
        assert result[0].id == "fc_xyz"

    def test_invalid_json_arguments(self):
        accum = {0: {"id": "x", "call_id": "x", "name": "fn", "arguments": "bad{"}}
        result = _build_tool_calls(accum)
        assert result is not None
        assert result[0].function.arguments == {}

    def test_empty_accum_returns_none(self):
        assert _build_tool_calls({}) is None

    def test_multiple_tool_calls_ordered(self):
        accum = {
            0: {"id": "a", "call_id": "ca", "name": "f1", "arguments": "{}"},
            1: {"id": "b", "call_id": "cb", "name": "f2", "arguments": "{}"},
        }
        result = _build_tool_calls(accum)
        assert result is not None
        assert result[0].id == "ca"
        assert result[1].id == "cb"


# ---------------------------------------------------------------------------
# _normalize_response
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNormalizeResponse:
    def test_content_only(self):
        raw = _FakeResponse(
            output=[_FakeOutputItem(type="message", content=[_FakeContentBlock(type="output_text", text="hello")])],
            usage=_FakeUsage(input_tokens=10, output_tokens=5),
        )
        result = _normalize_response(raw)
        assert result.message.content == "hello"
        assert result.message.tool_calls is None
        assert result.usage.prompt_tokens == 10
        assert result.usage.completion_tokens == 5
        assert result.done_reason == "stop"

    def test_tool_calls(self):
        raw = _FakeResponse(
            output=[
                _FakeOutputItem(
                    type="function_call",
                    name="search",
                    call_id="call_1",
                    arguments='{"q": "test"}',
                )
            ],
            status="completed",
        )
        result = _normalize_response(raw)
        assert result.message.tool_calls is not None
        assert len(result.message.tool_calls) == 1
        assert result.message.tool_calls[0].id == "call_1"
        assert result.message.tool_calls[0].function.name == "search"
        assert result.message.tool_calls[0].function.arguments == {"q": "test"}
        assert result.done_reason == "tool_calls"

    def test_reasoning_summary(self):
        raw = _FakeResponse(
            output=[
                _FakeOutputItem(type="message", content=[_FakeContentBlock(type="output_text", text="answer")]),
                _FakeReasoning(type="reasoning", summary=[_FakeSummary(type="summary_text", text="thinking...")]),
            ],
        )
        result = _normalize_response(raw)
        assert "thinking..." in (result.message.thinking or "")

    def test_invalid_tool_call_arguments(self):
        raw = _FakeResponse(
            output=[
                _FakeOutputItem(
                    type="function_call",
                    name="fn",
                    call_id="call_x",
                    arguments="bad{",
                )
            ],
        )
        result = _normalize_response(raw)
        assert result.message.tool_calls[0].function.arguments == {}


# ---------------------------------------------------------------------------
# _extract_usage
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractUsage:
    def test_none_usage(self):
        result = _extract_usage(None)
        assert result.prompt_tokens == 0
        assert result.completion_tokens == 0
        assert result.cache_read_tokens == 0

    def test_basic_usage(self):
        usage = _FakeUsage(input_tokens=100, output_tokens=50)
        result = _extract_usage(usage)
        assert result.prompt_tokens == 100
        assert result.completion_tokens == 50

    def test_cached_tokens(self):
        details = MagicMock()
        details.cached_tokens = 25
        usage = _FakeUsage(input_tokens=100, output_tokens=50, input_tokens_details=details)
        result = _extract_usage(usage)
        assert result.cache_read_tokens == 25


# ---------------------------------------------------------------------------
# Streaming: output_item.added after function_call_arguments.delta
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStreamingOutOfOrderEvents:
    """Verify that arguments accumulated before output_item.added are preserved.

    The bug: the output_item.added handler used to REPLACE tc_accum[idx],
    wiping any arguments that had already been accumulated from
    function_call_arguments.delta events that arrived first.

    The fix: output_item.added now updates the existing entry in-place,
    preserving the arguments field.
    """

    @pytest.mark.asyncio
    async def test_arguments_preserved_when_delta_arrives_first(self):
        """Simulate delta events arriving before output_item.added.

        This is the exact scenario the bug fix addresses.  If the API or a
        compatible endpoint sends function_call_arguments.delta before
        output_item.added, the accumulated arguments must survive.
        """
        from sdk.providers._openai_responses import OpenAIResponsesProvider

        # Build a fake async stream that yields events in reverse order:
        # 1. function_call_arguments.delta (arrives first)
        # 2. output_item.added (arrives second)
        # 3. response.completed

        item = _FakeItem(type="function_call", id="fc_abc", call_id="call_abc", name="get_weather")

        events = [
            _FakeEvent(
                type="response.function_call_arguments.delta",
                delta='{"location":',
                output_index=0,
            ),
            _FakeEvent(
                type="response.function_call_arguments.delta",
                delta=' "Paris"}',
                output_index=0,
            ),
            _FakeEvent(
                type="response.output_item.added",
                output_index=0,
                item=item,
            ),
            _FakeEvent(
                type="response.completed",
                response=_FakeResponse(
                    output=[
                        _FakeOutputItem(
                            type="function_call",
                            name="get_weather",
                            call_id="call_abc",
                            arguments='{"location": "Paris"}',
                        )
                    ],
                    status="completed",
                    usage=_FakeUsage(input_tokens=10, output_tokens=5),
                ),
            ),
        ]

        async def _fake_stream():
            for ev in events:
                yield ev

        # Create a provider instance and inject a mock client
        provider = OpenAIResponsesProvider.__new__(OpenAIResponsesProvider)
        provider._client = AsyncMock()
        provider._client.responses.create.return_value = _fake_stream()

        # Collect all deltas and the final response
        deltas = []
        final: ChatResponse | None = None
        async for chunk in provider.chat_stream(
            model="gpt-4o",
            messages=[{"role": "user", "content": "weather in Paris?"}],
            tools=[],
        ):
            if isinstance(chunk, ChatResponse):
                final = chunk
            else:
                deltas.append(chunk)

        # The final response must have the complete tool call with arguments
        assert final is not None
        assert final.message.tool_calls is not None
        assert len(final.message.tool_calls) == 1
        tc = final.message.tool_calls[0]
        assert tc.id == "call_abc"
        assert tc.function.name == "get_weather"
        assert tc.function.arguments == {"location": "Paris"}

    @pytest.mark.asyncio
    async def test_arguments_preserved_when_partial_delta_before_added(self):
        """Even a single partial delta before output_item.added must survive."""
        from sdk.providers._openai_responses import OpenAIResponsesProvider

        item = _FakeItem(type="function_call", id="fc_x", call_id="call_x", name="search")

        events = [
            _FakeEvent(
                type="response.function_call_arguments.delta",
                delta='{"q": "test"}',
                output_index=0,
            ),
            _FakeEvent(
                type="response.output_item.added",
                output_index=0,
                item=item,
            ),
            _FakeEvent(
                type="response.completed",
                response=_FakeResponse(
                    output=[
                        _FakeOutputItem(
                            type="function_call",
                            name="search",
                            call_id="call_x",
                            arguments='{"q": "test"}',
                        )
                    ],
                    status="completed",
                ),
            ),
        ]

        async def _fake_stream():
            for ev in events:
                yield ev

        provider = OpenAIResponsesProvider.__new__(OpenAIResponsesProvider)
        provider._client = AsyncMock()
        provider._client.responses.create.return_value = _fake_stream()

        final: ChatResponse | None = None
        async for chunk in provider.chat_stream(
            model="gpt-4o",
            messages=[{"role": "user", "content": "search"}],
            tools=[],
        ):
            if isinstance(chunk, ChatResponse):
                final = chunk

        assert final is not None
        assert final.message.tool_calls is not None
        assert final.message.tool_calls[0].function.arguments == {"q": "test"}

    @pytest.mark.asyncio
    async def test_normal_order_still_works(self):
        """The fix must not break the normal event order (added before delta)."""
        from sdk.providers._openai_responses import OpenAIResponsesProvider

        item = _FakeItem(type="function_call", id="fc_n", call_id="call_n", name="calc")

        events = [
            _FakeEvent(
                type="response.output_item.added",
                output_index=0,
                item=item,
            ),
            _FakeEvent(
                type="response.function_call_arguments.delta",
                delta='{"expr": "2+2"}',
                output_index=0,
            ),
            _FakeEvent(
                type="response.completed",
                response=_FakeResponse(
                    output=[
                        _FakeOutputItem(
                            type="function_call",
                            name="calc",
                            call_id="call_n",
                            arguments='{"expr": "2+2"}',
                        )
                    ],
                    status="completed",
                ),
            ),
        ]

        async def _fake_stream():
            for ev in events:
                yield ev

        provider = OpenAIResponsesProvider.__new__(OpenAIResponsesProvider)
        provider._client = AsyncMock()
        provider._client.responses.create.return_value = _fake_stream()

        final: ChatResponse | None = None
        async for chunk in provider.chat_stream(
            model="gpt-4o",
            messages=[{"role": "user", "content": "2+2"}],
            tools=[],
        ):
            if isinstance(chunk, ChatResponse):
                final = chunk

        assert final is not None
        assert final.message.tool_calls is not None
        assert final.message.tool_calls[0].function.name == "calc"
        assert final.message.tool_calls[0].function.arguments == {"expr": "2+2"}

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_out_of_order(self):
        """Multiple tool calls with mixed event ordering must all be correct."""
        from sdk.providers._openai_responses import OpenAIResponsesProvider

        item0 = _FakeItem(type="function_call", id="fc_a", call_id="call_a", name="f1")
        item1 = _FakeItem(type="function_call", id="fc_b", call_id="call_b", name="f2")

        events = [
            # Tool call 0: delta first, then added
            _FakeEvent(
                type="response.function_call_arguments.delta",
                delta='{"x": 1}',
                output_index=0,
            ),
            # Tool call 1: added first, then delta (normal order)
            _FakeEvent(
                type="response.output_item.added",
                output_index=1,
                item=item1,
            ),
            _FakeEvent(
                type="response.function_call_arguments.delta",
                delta='{"y": 2}',
                output_index=1,
            ),
            # Tool call 0: added late
            _FakeEvent(
                type="response.output_item.added",
                output_index=0,
                item=item0,
            ),
            _FakeEvent(
                type="response.completed",
                response=_FakeResponse(
                    output=[
                        _FakeOutputItem(type="function_call", name="f1", call_id="call_a", arguments='{"x": 1}'),
                        _FakeOutputItem(type="function_call", name="f2", call_id="call_b", arguments='{"y": 2}'),
                    ],
                    status="completed",
                ),
            ),
        ]

        async def _fake_stream():
            for ev in events:
                yield ev

        provider = OpenAIResponsesProvider.__new__(OpenAIResponsesProvider)
        provider._client = AsyncMock()
        provider._client.responses.create.return_value = _fake_stream()

        final: ChatResponse | None = None
        async for chunk in provider.chat_stream(
            model="gpt-4o",
            messages=[{"role": "user", "content": "multi"}],
            tools=[],
        ):
            if isinstance(chunk, ChatResponse):
                final = chunk

        assert final is not None
        assert final.message.tool_calls is not None
        assert len(final.message.tool_calls) == 2
        assert final.message.tool_calls[0].function.arguments == {"x": 1}
        assert final.message.tool_calls[1].function.arguments == {"y": 2}
