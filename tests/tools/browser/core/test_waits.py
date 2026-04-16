"""Tests for wait system improvements (BTI-018/019/024)."""

import pytest

from tools.browser.core.waits import SettleTimings


@pytest.mark.unit
class TestSettleTimings:
    """SettleTimings dataclass with content appearance phase."""

    def test_default_values(self):
        """Default timings have zero content appearance."""
        t = SettleTimings()
        assert t.content_appearance_ms == 0
        assert t.content_appearance_timed_out is False

    def test_total_ms_includes_content_appearance(self):
        """Total includes content appearance phase."""
        t = SettleTimings(
            network_idle_ms=100,
            font_ms=50,
            dom_quiet_ms=200,
            animation_ms=100,
            content_appearance_ms=300,
        )
        assert t.total_ms == 750

    def test_phases_includes_content_appearance(self):
        """Phases list includes content appearance."""
        t = SettleTimings()
        phase_names = [p[0] for p in t.phases]
        assert "content appearance" in phase_names

    def test_phases_count(self):
        """Five phases total (network, fonts, DOM, animations, content)."""
        t = SettleTimings()
        assert len(t.phases) == 5

    def test_content_appearance_timeout_flag(self):
        """Content appearance timeout flag works."""
        t = SettleTimings(content_appearance_timed_out=True)
        phase = [p for p in t.phases if p[0] == "content appearance"][0]
        assert phase[2] is True  # timed_out

    def test_all_phases_present(self):
        """All five phases are in the correct order."""
        t = SettleTimings()
        phase_names = [p[0] for p in t.phases]
        assert phase_names == [
            "network idle",
            "fonts",
            "DOM quiet",
            "animations",
            "content appearance",
        ]