"""Tests for browser tool string formatters."""

from __future__ import annotations

import pytest

from tools.browser.core._formatting import (
    format_javascript_result,
    format_page_view,
    format_save_result,
)


@pytest.mark.unit
class TestFormatJavascriptResult:
    """Tests for format_javascript_result."""

    def test_success_with_result(self) -> None:
        """Success with a JSON-serializable return value."""
        out = format_javascript_result(success=True, result={"key": "value"})
        assert out.startswith("[JavaScript: success]")
        assert 'Result: {"key": "value"}' in out

    def test_success_none_result(self) -> None:
        """Result line is omitted when result is None."""
        out = format_javascript_result(success=True, result=None)
        assert "Result:" not in out
        assert "[JavaScript: success]" in out

    def test_success_with_console(self) -> None:
        """Console output is pipe-separated."""
        out = format_javascript_result(
            success=True, result=42, console_output=["line one", "line two"],
        )
        assert "Console: line one | line two" in out

    def test_console_omitted_when_empty(self) -> None:
        """Console line is omitted when there's no output."""
        out = format_javascript_result(success=True, result=1, console_output=None)
        assert "Console:" not in out

    def test_error(self) -> None:
        """Error message is shown on failure."""
        out = format_javascript_result(
            success=False, error="timed out", console_output=["partial"],
        )
        assert "[JavaScript: error]" in out
        assert "Error: timed out" in out
        assert "Console: partial" in out

    def test_non_serializable_result(self) -> None:
        """Non-JSON-serializable results fall back to repr."""
        out = format_javascript_result(success=True, result={1, 2, 3})
        assert "Result:" in out


@pytest.mark.unit
class TestFormatSaveResult:
    """Tests for format_save_result."""

    def test_basic(self) -> None:
        """Produces the expected bracket format."""
        out = format_save_result(
            filename="page.md",
            container_path="/home/computron/page.md",
            size_bytes=12345,
        )
        assert out == "[Saved: page.md | /home/computron/page.md | 12345 bytes]"


@pytest.mark.unit
class TestFormatPageView:
    """Tests for format_page_view."""

    def test_basic_page(self) -> None:
        """Standard page view with viewport."""
        out = format_page_view(
            title="Example",
            url="https://example.com",
            status_code=200,
            viewport={"scroll_top": 0, "viewport_height": 800, "document_height": 2000},
            content="Hello world",
            truncated=False,
        )
        assert "[Page: Example | https://example.com | 200]" in out
        assert "[Viewport: 0-800 of 2000px]" in out
        assert "Hello world" in out

    def test_truncated_flag(self) -> None:
        """Truncated flag appears in viewport line."""
        out = format_page_view(
            title="T",
            url="u",
            status_code=None,
            viewport={"scroll_top": 0, "viewport_height": 800, "document_height": 2000},
            content="",
            truncated=True,
        )
        assert "truncated" in out

    def test_no_viewport(self) -> None:
        """Missing viewport shows unavailable."""
        out = format_page_view(
            title="T",
            url="u",
            status_code=None,
            viewport=None,
            content="",
            truncated=False,
        )
        assert "[Viewport: unavailable]" in out
