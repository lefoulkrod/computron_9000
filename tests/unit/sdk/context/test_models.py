"""Tests for context management data models."""

import pytest

from sdk.context import ContextStats


@pytest.mark.unit
def test_context_stats_defaults():
    stats = ContextStats()
    assert stats.context_used == 0
    assert stats.context_limit == 0
    assert stats.fill_ratio == 0.0


@pytest.mark.unit
def test_context_stats_fill_ratio_calculation():
    stats = ContextStats(context_used=64000, context_limit=128000)
    assert stats.fill_ratio == pytest.approx(0.5)


@pytest.mark.unit
def test_context_stats_fill_ratio_at_limit():
    stats = ContextStats(context_used=128000, context_limit=128000)
    assert stats.fill_ratio == pytest.approx(1.0)


@pytest.mark.unit
def test_context_stats_fill_ratio_over_limit():
    stats = ContextStats(context_used=140000, context_limit=128000)
    assert stats.fill_ratio > 1.0


@pytest.mark.unit
def test_context_stats_fill_ratio_zero_limit():
    """Returns 0.0 when context_limit is zero (unknown/unset)."""
    stats = ContextStats(context_used=1000, context_limit=0)
    assert stats.fill_ratio == 0.0
