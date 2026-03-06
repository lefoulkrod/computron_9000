"""Tests for token tracking and counting."""

import pytest

from agents.ollama.sdk.context import OllamaTokenCounter, TokenTracker, TokenUsage


class _FakeResponse:
    """Mimics Ollama ChatResponse with token count attributes."""

    def __init__(self, prompt_eval_count: int = 0, eval_count: int = 0):
        self.prompt_eval_count = prompt_eval_count
        self.eval_count = eval_count


@pytest.mark.unit
class TestOllamaTokenCounter:
    """Tests for the OllamaTokenCounter."""

    def test_extract_usage(self):
        counter = OllamaTokenCounter()
        usage = counter.extract_usage(_FakeResponse(prompt_eval_count=1000, eval_count=200))
        assert usage.prompt_tokens == 1000
        assert usage.completion_tokens == 200

    def test_extract_usage_missing_attrs(self):
        """Gracefully handles objects without token count attributes."""
        counter = OllamaTokenCounter()
        usage = counter.extract_usage(object())
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0

    def test_extract_usage_none_values(self):
        """Handles None values for token counts."""
        counter = OllamaTokenCounter()
        resp = _FakeResponse()
        resp.prompt_eval_count = None  # type: ignore[assignment]
        resp.eval_count = None  # type: ignore[assignment]
        usage = counter.extract_usage(resp)
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0


@pytest.mark.unit
class TestTokenTracker:
    """Tests for the TokenTracker."""

    def test_initial_stats(self):
        tracker = TokenTracker(OllamaTokenCounter(), context_limit=128000)
        stats = tracker.stats
        assert stats.context_used == 0
        assert stats.context_limit == 128000
        assert stats.fill_ratio == 0.0

    def test_last_usage_initially_none(self):
        tracker = TokenTracker(OllamaTokenCounter())
        assert tracker.last_usage is None

    def test_record_updates_stats(self):
        tracker = TokenTracker(OllamaTokenCounter(), context_limit=128000)
        resp = _FakeResponse(prompt_eval_count=100000, eval_count=5000)
        usage = tracker.record(resp)

        assert usage == TokenUsage(prompt_tokens=100000, completion_tokens=5000)
        assert tracker.stats.context_used == 105000
        assert tracker.stats.fill_ratio == pytest.approx(105000 / 128000)

    def test_record_overwrites_previous(self):
        """Each record replaces the previous stats (not cumulative)."""
        tracker = TokenTracker(OllamaTokenCounter(), context_limit=128000)
        tracker.record(_FakeResponse(prompt_eval_count=50000, eval_count=1000))
        tracker.record(_FakeResponse(prompt_eval_count=80000, eval_count=2000))

        assert tracker.stats.context_used == 82000
        assert tracker.last_usage == TokenUsage(prompt_tokens=80000, completion_tokens=2000)
