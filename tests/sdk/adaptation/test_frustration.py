"""Tests for frustration detection module."""

import pytest

from sdk.adaptation import FrustrationDetector, FrustrationLevel, detect_frustration


class TestFrustrationDetector:
    """Test cases for frustration detection."""

    @pytest.fixture
    def detector(self):
        return FrustrationDetector()

    def test_no_frustration(self, detector):
        """Normal messages should return NONE level."""
        result = detector.detect("Hello, can you help me with Python?")
        assert result.level == FrustrationLevel.NONE
        assert result.score == 0.0
        assert not result.is_frustrated()

    def test_some_frustration_detected(self, detector):
        """Detect frustration indicators."""
        result = detector.detect("This is frustrating and confusing!")
        assert result.level != FrustrationLevel.NONE
        assert result.score > 0
        assert len(result.matched_patterns) > 0
        assert result.is_frustrated()

    def test_high_frustration(self, detector):
        """Detect high frustration with strong language."""
        result = detector.detect("This is stupid! It's completely broken!!!")
        assert result.level == FrustrationLevel.HIGH
        assert result.score >= 0.8

    def test_consecutive_frustration_tracking(self, detector):
        """Test that user state tracks consecutive frustrated turns."""
        from sdk.adaptation import UserState

        state = UserState()

        state.update_frustration(FrustrationLevel.LOW, 0.2)
        assert state.consecutive_frustrated_turns == 1

        state.update_frustration(FrustrationLevel.MEDIUM, 0.5)
        assert state.consecutive_frustrated_turns == 2

        state.update_frustration(FrustrationLevel.NONE, 0.0)
        assert state.consecutive_frustrated_turns == 0

    def test_case_insensitive(self, detector):
        """Detection should be case-insensitive."""
        result1 = detector.detect("This is STUPID")
        result2 = detector.detect("This is stupid")
        assert result1.level == result2.level

    @pytest.mark.parametrize("message,expected_level", [
        ("This is frustrating", FrustrationLevel.MEDIUM),
        ("This is garbage!", FrustrationLevel.HIGH),
        ("Total waste of time", FrustrationLevel.HIGH),
        ("Works perfectly thanks!", FrustrationLevel.NONE),
    ])
    def test_frustration_patterns(self, detector, message, expected_level):
        """Test specific frustration patterns."""
        result = detector.detect(message)
        assert result.level == expected_level, f"Failed for: {message}"

    def test_frustration_result_is_frustrated(self, detector):
        """Test is_frustrated() method for all levels."""
        none_result = detector.detect("This is great!")
        assert not none_result.is_frustrated()

        low_result = detector.detect("Still waiting...")
        assert low_result.is_frustrated()

        medium_result = detector.detect("This is frustrating!")
        assert medium_result.is_frustrated()

        high_result = detector.detect("This is garbage!!!")
        assert high_result.is_frustrated()

    def test_detect_convenience_function(self):
        """Test the convenience function detect_frustration."""
        result = detect_frustration("This is terrible!")
        assert result.is_frustrated()
        assert result.level == FrustrationLevel.HIGH
