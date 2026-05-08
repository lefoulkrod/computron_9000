"""Tests for context management data models."""

import pytest

from sdk.context import ContextStats, TokenUsage


@pytest.mark.unit
class TestTokenUsage:
    """Tests for the TokenUsage model."""

    def test_defaults(self):
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0

    def test_custom_values(self):
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50)
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50


@pytest.mark.unit
class TestContextStats:
    """Tests for the ContextStats model."""

    def test_defaults(self):
        stats = ContextStats()
        assert stats.context_used == 0
        assert stats.context_limit == 0
        assert stats.fill_ratio == 0.0

    def test_fill_ratio_calculation(self):
        stats = ContextStats(context_used=64000, context_limit=128000)
        assert stats.fill_ratio == pytest.approx(0.5)

    def test_fill_ratio_at_limit(self):
        stats = ContextStats(context_used=128000, context_limit=128000)
        assert stats.fill_ratio == pytest.approx(1.0)

    def test_fill_ratio_over_limit(self):
        stats = ContextStats(context_used=140000, context_limit=128000)
        assert stats.fill_ratio > 1.0

    def test_fill_ratio_zero_limit(self):
        """Returns 0.0 when context_limit is zero (unknown/unset)."""
        stats = ContextStats(context_used=1000, context_limit=0)
        assert stats.fill_ratio == 0.0
