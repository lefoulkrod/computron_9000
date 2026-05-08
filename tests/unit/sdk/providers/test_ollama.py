"""Tests for OllamaProvider response normalization."""

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from sdk.providers._ollama import OllamaProvider, _normalize_response, _wrap_ollama_error


@dataclass
class _FakeFunc:
    name: str
    arguments: dict[str, Any]


@dataclass
class _FakeToolCall:
    function: _FakeFunc


@dataclass
class _FakeMessage:
    content: str | None = None
    thinking: str | None = None
    tool_calls: list[_FakeToolCall] | None = None


@dataclass
class _FakeOllamaResponse:
    message: _FakeMessage = field(default_factory=_FakeMessage)
    prompt_eval_count: int = 0
    eval_count: int = 0
    done_reason: str | None = None
    done: bool = True
    total_duration: int = 0
    load_duration: int = 0
    prompt_eval_duration: int = 0
    eval_duration: int = 0


@pytest.mark.unit
class TestNormalizeResponse:
    def test_content_only(self):
        raw = _FakeOllamaResponse(
            message=_FakeMessage(content="hello"),
            prompt_eval_count=100,
            eval_count=50,
        )
        result = _normalize_response(raw)
        assert result.message.content == "hello"
        assert result.message.thinking is None
        assert result.message.tool_calls is None
        assert result.usage.prompt_tokens == 100
        assert result.usage.completion_tokens == 50
        assert result.raw is raw

    def test_thinking(self):
        raw = _FakeOllamaResponse(
            message=_FakeMessage(content="answer", thinking="reasoning"),
        )
        result = _normalize_response(raw)
        assert result.message.thinking == "reasoning"

    def test_tool_calls(self):
        tc = _FakeToolCall(_FakeFunc(name="search", arguments={"q": "test"}))
        raw = _FakeOllamaResponse(
            message=_FakeMessage(tool_calls=[tc]),
        )
        result = _normalize_response(raw)
        assert result.message.tool_calls is not None
        assert len(result.message.tool_calls) == 1
        assert result.message.tool_calls[0].function.name == "search"
        assert result.message.tool_calls[0].function.arguments == {"q": "test"}
        assert result.message.tool_calls[0].id is None

    def test_done_reason(self):
        raw = _FakeOllamaResponse(done_reason="stop")
        result = _normalize_response(raw)
        assert result.done_reason == "stop"

    def test_zero_token_counts(self):
        raw = _FakeOllamaResponse(prompt_eval_count=0, eval_count=0)
        result = _normalize_response(raw)
        assert result.usage.prompt_tokens == 0
        assert result.usage.completion_tokens == 0

    def test_none_token_counts(self):
        """Ollama may return None for token counts on empty responses."""
        raw = _FakeOllamaResponse()
        raw.prompt_eval_count = None  # type: ignore[assignment]
        raw.eval_count = None  # type: ignore[assignment]
        result = _normalize_response(raw)
        assert result.usage.prompt_tokens == 0
        assert result.usage.completion_tokens == 0


async def _async_iter(items):
    """Wrap items into an async iterator, mimicking Ollama's streaming response."""
    for item in items:
        yield item


@pytest.mark.unit
class TestOllamaProviderChat:
    @pytest.mark.asyncio
    async def test_chat_delegates_to_client(self):
        """Provider.chat calls the underlying AsyncClient.chat and normalizes."""
        # Streaming distributes content across chunks; final chunk has stats only.
        chunk1 = _FakeOllamaResponse(message=_FakeMessage(content="response "))
        chunk2 = _FakeOllamaResponse(message=_FakeMessage(content="text"))
        final = _FakeOllamaResponse(
            message=_FakeMessage(content=""),
            prompt_eval_count=200,
            eval_count=80,
        )
        provider = OllamaProvider.__new__(OllamaProvider)
        provider._client = AsyncMock()
        provider._client.chat.return_value = _async_iter([chunk1, chunk2, final])

        result = await provider.chat(
            model="test-model",
            messages=[{"role": "user", "content": "hi"}],
        )

        provider._client.chat.assert_called_once()
        call_kwargs = provider._client.chat.call_args.kwargs
        assert call_kwargs["model"] == "test-model"
        assert call_kwargs["stream"] is True
        assert result.message.content == "response text"
        assert result.usage.prompt_tokens == 200


@pytest.mark.unit
class TestWrapOllamaError:
    def test_response_error_400_not_retryable(self):
        """Client errors like 400 should not be retried."""
        from ollama import ResponseError

        exc = ResponseError("does not support thinking", status_code=400)
        wrapped = _wrap_ollama_error(exc)
        assert wrapped.retryable is False
        assert wrapped.status_code == 400

    def test_response_error_500_retryable(self):
        """Server errors like 500 should be retried."""
        from ollama import ResponseError

        exc = ResponseError("internal server error", status_code=500)
        wrapped = _wrap_ollama_error(exc)
        assert wrapped.retryable is True
        assert wrapped.status_code == 500

    def test_connection_error_retryable(self):
        """Non-HTTP errors (connection issues) should be retried."""
        exc = ConnectionError("refused")
        wrapped = _wrap_ollama_error(exc)
        assert wrapped.retryable is True
        assert wrapped.status_code is None


@pytest.mark.unit
class TestOllamaProviderListModels:
    @pytest.mark.asyncio
    async def test_list_models(self):
        provider = OllamaProvider.__new__(OllamaProvider)
        provider._client = AsyncMock()
        model1 = MagicMock()
        model1.model = "llama3:8b"
        model2 = MagicMock()
        model2.model = "mistral:7b"
        model3 = MagicMock()
        model3.model = None
        provider._client.list.return_value = MagicMock(models=[model1, model2, model3])

        result = await provider.list_models()
        assert result == ["llama3:8b", "mistral:7b"]
