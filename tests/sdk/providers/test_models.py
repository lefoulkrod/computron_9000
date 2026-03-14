"""Tests for provider response model round-trip serialization."""

import pytest

from sdk.providers._models import (
    ChatMessage,
    ChatResponse,
    TokenUsage,
    ToolCall,
    ToolCallFunction,
)


@pytest.mark.unit
class TestToolCallFunction:
    def test_basic_creation(self):
        f = ToolCallFunction(name="search", arguments={"query": "test"})
        assert f.name == "search"
        assert f.arguments == {"query": "test"}

    def test_empty_arguments(self):
        f = ToolCallFunction(name="noop", arguments={})
        assert f.arguments == {}


@pytest.mark.unit
class TestToolCall:
    def test_with_id(self):
        tc = ToolCall(
            id="call_123",
            function=ToolCallFunction(name="search", arguments={"q": "hi"}),
        )
        assert tc.id == "call_123"
        assert tc.function.name == "search"

    def test_without_id(self):
        tc = ToolCall(
            function=ToolCallFunction(name="search", arguments={}),
        )
        assert tc.id is None


@pytest.mark.unit
class TestChatMessage:
    def test_content_only(self):
        msg = ChatMessage(content="hello")
        assert msg.content == "hello"
        assert msg.thinking is None
        assert msg.tool_calls is None

    def test_with_tool_calls(self):
        tc = ToolCall(function=ToolCallFunction(name="fn", arguments={}))
        msg = ChatMessage(tool_calls=[tc])
        assert msg.content is None
        assert len(msg.tool_calls) == 1

    def test_with_thinking(self):
        msg = ChatMessage(content="answer", thinking="reasoning")
        assert msg.thinking == "reasoning"


@pytest.mark.unit
class TestTokenUsage:
    def test_defaults(self):
        u = TokenUsage()
        assert u.prompt_tokens == 0
        assert u.completion_tokens == 0

    def test_explicit_values(self):
        u = TokenUsage(prompt_tokens=100, completion_tokens=50)
        assert u.prompt_tokens == 100
        assert u.completion_tokens == 50


@pytest.mark.unit
class TestChatResponse:
    def test_minimal(self):
        r = ChatResponse(message=ChatMessage(content="hi"))
        assert r.message.content == "hi"
        assert r.usage.prompt_tokens == 0
        assert r.done_reason is None
        assert r.raw is None

    def test_round_trip_json(self):
        tc = ToolCall(
            id="call_1",
            function=ToolCallFunction(name="browse", arguments={"url": "example.com"}),
        )
        r = ChatResponse(
            message=ChatMessage(content="result", thinking="thought", tool_calls=[tc]),
            usage=TokenUsage(prompt_tokens=500, completion_tokens=100),
            done_reason="stop",
        )
        data = r.model_dump(mode="json")
        restored = ChatResponse.model_validate(data)
        assert restored.message.content == "result"
        assert restored.message.thinking == "thought"
        assert len(restored.message.tool_calls) == 1
        assert restored.message.tool_calls[0].id == "call_1"
        assert restored.usage.prompt_tokens == 500
        assert restored.done_reason == "stop"

    def test_raw_field_arbitrary_type(self):
        """raw can hold any provider-specific response object."""
        sentinel = object()
        r = ChatResponse(message=ChatMessage(), raw=sentinel)
        assert r.raw is sentinel
