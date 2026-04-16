"""Tests for tracking URL unwrapping (BTI-017)."""

from __future__ import annotations

import pytest

from tools.browser.core.browser import Browser


@pytest.mark.unit
class TestUnwrapTrackingUrl:
    """Tests for Browser._unwrap_tracking_url."""

    def test_facebook_tracking_redirect(self) -> None:
        """Unwraps l.facebook.com tracking redirect to actual URL."""
        url = "https://l.facebook.com/l.php?u=https%3A%2F%2Fexample.com%2Fpage"
        result = Browser._unwrap_tracking_url(url)
        assert result == "https://example.com/page"

    def test_facebook_lm_tracking_redirect(self) -> None:
        """Unwraps lm.facebook.com tracking redirect to actual URL."""
        url = "https://lm.facebook.com/l.php?u=https%3A%2F%2Fexample.org%2Farticle"
        result = Browser._unwrap_tracking_url(url)
        assert result == "https://example.org/article"

    def test_non_tracking_url_unchanged(self) -> None:
        """Non-tracking URLs are returned unchanged."""
        url = "https://www.google.com/search?q=test"
        result = Browser._unwrap_tracking_url(url)
        assert result == url

    def test_facebook_url_without_u_param(self) -> None:
        """Facebook tracking URL without 'u' param returns original."""
        url = "https://l.facebook.com/l.php?h=abc123"
        result = Browser._unwrap_tracking_url(url)
        assert result == url

    def test_invalid_url_returns_original(self) -> None:
        """Invalid URLs are returned unchanged."""
        result = Browser._unwrap_tracking_url("not-a-url")
        assert result == "not-a-url"

    def test_empty_string_returns_empty(self) -> None:
        """Empty string is returned unchanged."""
        result = Browser._unwrap_tracking_url("")
        assert result == ""

    def test_regular_facebook_url_unchanged(self) -> None:
        """Regular facebook.com URLs (not tracking) are returned unchanged."""
        url = "https://www.facebook.com/profile.php?id=123"
        result = Browser._unwrap_tracking_url(url)
        assert result == url