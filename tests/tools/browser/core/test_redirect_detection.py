"""Tests for cross-domain redirect detection (BTI-001, BTI-003, etc.)."""

from __future__ import annotations

import pytest

from tools.browser.core.browser import _extract_registered_domain


@pytest.mark.unit
class TestExtractRegisteredDomain:
    """Tests for _extract_registered_domain helper."""

    def test_simple_domain(self) -> None:
        """Extracts registered domain from a simple URL."""
        assert _extract_registered_domain("https://www.google.com/search") == "google.com"

    def test_subdomain_stripped(self) -> None:
        """Strips subdomains to return the registered domain."""
        assert _extract_registered_domain("https://l.facebook.com/l.php?u=xyz") == "facebook.com"

    def test_bare_domain(self) -> None:
        """Returns the domain as-is when no subdomain is present."""
        assert _extract_registered_domain("https://example.com/page") == "example.com"

    def test_two_part_tld(self) -> None:
        """Returns last two parts for two-part TLDs (simplified)."""
        assert _extract_registered_domain("https://www.example.co.uk/path") == "co.uk"

    def test_invalid_url(self) -> None:
        """Returns empty string for invalid URLs."""
        assert _extract_registered_domain("not-a-url") == ""

    def test_empty_string(self) -> None:
        """Returns empty string for empty input."""
        assert _extract_registered_domain("") == ""

    def test_url_without_path(self) -> None:
        """Handles URLs with no path component."""
        assert _extract_registered_domain("https://reddit.com") == "reddit.com"

    def test_deep_subdomain(self) -> None:
        """Strips deep subdomains to return the registered domain."""
        assert _extract_registered_domain("https://a.b.c.example.com/page") == "example.com"

    def test_about_blank(self) -> None:
        """Returns empty string for about:blank URLs."""
        assert _extract_registered_domain("about:blank") == ""

    def test_localhost(self) -> None:
        """Handles localhost URLs."""
        assert _extract_registered_domain("http://localhost:8080/page") == "localhost"