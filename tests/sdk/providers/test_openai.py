"""Tests for OpenAIProvider message conversion, normalization, and caching."""

import json
import time
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from sdk.providers._models import ProviderError
from sdk.providers._openai import (
    OpenAIProvider,
    _build_tool_calls,
    _convert_messages_for_openai,
    _normalize_response,
    _wrap_error,
)


# ---------------------------------------------------------------------------
# Fake response objects (no openai dep needed)
# ---------------------------------------------------------------------------


@dataclass
class _FakeFunction:
    name: str
    arguments: str  # JSON string, as OpenAI sends it


@dataclass
class _FakeToolCall:
    id: str
    function: _FakeFunction


@dataclass
class _FakeMessage:
    content: str | None = None
    tool_calls: list[_FakeToolCall] | None = None


@dataclass
class _FakeChoice:
    message: _FakeMessage
    finish_reason: str | None = None


@dataclass
class _FakeUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class _FakeResponse:
    choices: list[_FakeChoice]
    usage: _FakeUsage = field(default_factory=_FakeUsage)


# ---------------------------------------------------------------------------
# _convert_messages_for_openai
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConvertMessagesForOpenAI:
    def test_user_message_passes_through(self):
        """User messages are returned unchanged."""
        msgs = [{"role": "user", "content": "hello"}]
        result = _convert_messages_for_openai(msgs)
        assert result == msgs

    def test_assistant_message_without_tool_calls_passes_through(self):
        """Plain assistant messages need no conversion."""
        msgs = [{"role": "assistant", "content": "hi"}]
        result = _convert_messages_for_openai(msgs)
        assert result == msgs

    def test_tool_call_arguments_serialized_to_json_string(self):
        """dict arguments must become a JSON string for OpenAI."""
        msgs = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "search", "arguments": {"query": "test"}},
                    }
                ],
            }
        ]
        result = _convert_messages_for_openai(msgs)
        tc = result[0]["tool_calls"][0]
        assert tc["type"] == "function"
        assert tc["id"] == "call_1"
        assert isinstance(tc["function"]["arguments"], str)
        assert json.loads(tc["function"]["arguments"]) == {"query": "test"}

    def test_tool_call_arguments_already_string_preserved(self):
        """If arguments are already a string, they pass through as-is."""
        msgs = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_2",
                        "function": {"name": "fn", "arguments": '{"k": "v"}'},
                    }
                ],
            }
        ]
        result = _convert_messages_for_openai(msgs)
        assert result[0]["tool_calls"][0]["function"]["arguments"] == '{"k": "v"}'

    def test_multiple_tool_calls(self):
        """Multiple tool calls in one message are all converted."""
        msgs = [
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "a", "function": {"name": "f1", "arguments": {"x": 1}}},
                    {"id": "b", "function": {"name": "f2", "arguments": {"y": 2}}},
                ],
            }
        ]
        result = _convert_messages_for_openai(msgs)
        args0 = json.loads(result[0]["tool_calls"][0]["function"]["arguments"])
        args1 = json.loads(result[0]["tool_calls"][1]["function"]["arguments"])
        assert args0 == {"x": 1}
        assert args1 == {"y": 2}


# ---------------------------------------------------------------------------
# _build_tool_calls
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildToolCalls:
    def test_valid_json_arguments(self):
        """Accumulated JSON string is parsed into a dict."""
        accum = {0: {"id": "call_1", "name": "search", "arguments": '{"q": "hello"}'}}
        result = _build_tool_calls(accum)
        assert result is not None
        assert len(result) == 1
        assert result[0].id == "call_1"
        assert result[0].function.name == "search"
        assert result[0].function.arguments == {"q": "hello"}

    def test_invalid_json_arguments_becomes_empty_dict(self):
        """If arguments can't be parsed, fall back to empty dict."""
        accum = {0: {"id": "x", "name": "fn", "arguments": "not-json{"}}
        result = _build_tool_calls(accum)
        assert result is not None
        assert result[0].function.arguments == {}

    def test_empty_accum_returns_none(self):
        """Empty accumulator produces None (no tool calls)."""
        result = _build_tool_calls({})
        assert result is None

    def test_multiple_tool_calls_ordered_by_index(self):
        """Tool calls are produced in index order."""
        accum = {
            0: {"id": "first", "name": "f1", "arguments": "{}"},
            1: {"id": "second", "name": "f2", "arguments": "{}"},
        }
        result = _build_tool_calls(accum)
        assert result is not None
        assert result[0].id == "first"
        assert result[1].id == "second"


# ---------------------------------------------------------------------------
# _normalize_response
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNormalizeResponse:
    def test_content_only(self):
        raw = _FakeResponse(
            choices=[_FakeChoice(message=_FakeMessage(content="hello"), finish_reason="stop")],
            usage=_FakeUsage(prompt_tokens=10, completion_tokens=5),
        )
        result = _normalize_response(raw)
        assert result.message.content == "hello"
        assert result.message.tool_calls is None
        assert result.usage.prompt_tokens == 10
        assert result.usage.completion_tokens == 5
        assert result.done_reason == "stop"
        assert result.raw is raw

    def test_tool_calls(self):
        tc = _FakeToolCall(
            id="call_1",
            function=_FakeFunction(name="search", arguments='{"q": "test"}'),
        )
        raw = _FakeResponse(
            choices=[_FakeChoice(message=_FakeMessage(tool_calls=[tc]), finish_reason="tool_calls")],
        )
        result = _normalize_response(raw)
        assert result.message.tool_calls is not None
        assert len(result.message.tool_calls) == 1
        assert result.message.tool_calls[0].id == "call_1"
        assert result.message.tool_calls[0].function.name == "search"
        assert result.message.tool_calls[0].function.arguments == {"q": "test"}
        assert result.done_reason == "tool_calls"

    def test_invalid_tool_call_arguments_become_empty(self):
        tc = _FakeToolCall(id="x", function=_FakeFunction(name="fn", arguments="bad{"))
        raw = _FakeResponse(choices=[_FakeChoice(message=_FakeMessage(tool_calls=[tc]))])
        result = _normalize_response(raw)
        assert result.message.tool_calls[0].function.arguments == {}

    def test_finish_reason_mapped(self):
        raw = _FakeResponse(choices=[_FakeChoice(message=_FakeMessage(content="hi"), finish_reason="length")])
        result = _normalize_response(raw)
        assert result.done_reason == "length"

    def test_no_usage(self):
        raw = _FakeResponse(choices=[_FakeChoice(message=_FakeMessage(content="hi"))], usage=None)
        result = _normalize_response(raw)
        assert result.usage.prompt_tokens == 0
        assert result.usage.completion_tokens == 0


# ---------------------------------------------------------------------------
# _wrap_error
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWrapError:
    def test_generic_exception_not_retryable(self):
        exc = RuntimeError("something failed")
        result = _wrap_error(exc)
        assert isinstance(result, ProviderError)
        assert result.retryable is False
        assert result.status_code is None
        assert result.__cause__ is exc


# ---------------------------------------------------------------------------
# OpenAIProvider — model cache
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOpenAIProviderModelCache:
    def _make_provider(self) -> OpenAIProvider:
        provider = OpenAIProvider.__new__(OpenAIProvider)
        provider._model_cache = None
        provider._model_cache_at = 0.0
        return provider

    @pytest.mark.asyncio
    async def test_cache_hit_skips_client(self):
        """Cached result is returned without calling the client."""
        provider = self._make_provider()
        provider._model_cache = ["gpt-4", "gpt-3.5-turbo"]
        provider._model_cache_at = time.monotonic()  # fresh

        provider._client = AsyncMock()
        result = await provider.list_models()

        assert result == ["gpt-4", "gpt-3.5-turbo"]
        provider._client.models.list.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_fetches_from_client(self):
        """Expired cache triggers a client call and populates cache."""
        provider = self._make_provider()
        provider._model_cache_at = 0.0  # expired

        m1, m2 = MagicMock(), MagicMock()
        m1.id = "gpt-4"
        m2.id = "gpt-3.5-turbo"
        provider._client = AsyncMock()
        provider._client.models.list.return_value = MagicMock(data=[m1, m2])

        result = await provider.list_models()
        assert result == ["gpt-4", "gpt-3.5-turbo"]
        assert provider._model_cache == ["gpt-4", "gpt-3.5-turbo"]

    def test_invalidate_clears_cache(self):
        """invalidate_model_cache resets both cache fields."""
        provider = self._make_provider()
        provider._model_cache = ["gpt-4"]
        provider._model_cache_at = time.monotonic()

        provider.invalidate_model_cache()

        assert provider._model_cache is None
        assert provider._model_cache_at == 0.0

    @pytest.mark.asyncio
    async def test_invalidate_then_fetch(self):
        """After invalidation, next list_models call fetches fresh data."""
        provider = self._make_provider()
        provider._model_cache = ["old-model"]
        provider._model_cache_at = time.monotonic()
        provider.invalidate_model_cache()

        m = MagicMock()
        m.id = "new-model"
        provider._client = AsyncMock()
        provider._client.models.list.return_value = MagicMock(data=[m])

        result = await provider.list_models()
        assert result == ["new-model"]
