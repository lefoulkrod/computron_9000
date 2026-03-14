"""Tests for the ScratchpadHook Rich panel logging."""

import json
from io import StringIO
from unittest.mock import patch

import pytest

from sdk.hooks._scratchpad_hook import ScratchpadHook


@pytest.fixture()
def hook():
    return ScratchpadHook()


@pytest.mark.unit
class TestScratchpadHookPassthrough:
    """Non-scratchpad tools are passed through unchanged."""

    def test_ignores_unrelated_tool(self, hook):
        result = hook.after_tool("open_url", {"url": "http://example.com"}, "ok")
        assert result == "ok"

    def test_returns_result_unchanged(self, hook):
        result = hook.after_tool("click", {"ref": "7"}, "clicked")
        assert result == "clicked"


@pytest.mark.unit
class TestScratchpadHookWrite:
    """Panels for save_to_scratchpad."""

    def test_save_prints_panel(self, hook):
        """The hook prints a green panel with key and value."""
        buf = StringIO()
        hook._console = _make_console(buf)

        tool_result = str({"status": "ok", "key": "card_3", "value": "queen"})
        result = hook.after_tool(
            "save_to_scratchpad", {"key": "card_3", "value": "queen"}, tool_result
        )

        assert result == tool_result
        output = buf.getvalue()
        assert "Scratchpad Write" in output
        assert "card_3" in output
        assert "queen" in output

    def test_save_truncates_long_value(self, hook):
        """Values longer than 200 chars are truncated in the panel."""
        buf = StringIO()
        hook._console = _make_console(buf)

        long_value = "x" * 300
        hook.after_tool(
            "save_to_scratchpad",
            {"key": "big", "value": long_value},
            str({"status": "ok", "key": "big", "value": long_value}),
        )

        output = buf.getvalue()
        assert "…" in output


@pytest.mark.unit
class TestScratchpadHookRead:
    """Panels for recall_from_scratchpad."""

    def test_recall_single_key(self, hook):
        """The hook prints a cyan panel with the recalled key and value."""
        buf = StringIO()
        hook._console = _make_console(buf)

        tool_result = json.dumps({"status": "ok", "key": "card_3", "value": "queen"})
        result = hook.after_tool(
            "recall_from_scratchpad", {"key": "card_3"}, tool_result
        )

        assert result == tool_result
        output = buf.getvalue()
        assert "Scratchpad Read" in output
        assert "card_3" in output
        assert "queen" in output

    def test_recall_all_items(self, hook):
        """Recall with no key shows all stored items."""
        buf = StringIO()
        hook._console = _make_console(buf)

        tool_result = json.dumps({"status": "ok", "items": {"a": "1", "b": "2"}})
        hook.after_tool("recall_from_scratchpad", {}, tool_result)

        output = buf.getvalue()
        assert "2 items" in output
        assert "a:" in output
        assert "b:" in output

    def test_recall_empty(self, hook):
        """Recall all on empty scratchpad shows empty message."""
        buf = StringIO()
        hook._console = _make_console(buf)

        tool_result = json.dumps({"status": "ok", "items": {}})
        hook.after_tool("recall_from_scratchpad", {}, tool_result)

        output = buf.getvalue()
        assert "empty" in output

    def test_recall_not_found(self, hook):
        """Recall of a missing key shows not-found styling."""
        buf = StringIO()
        hook._console = _make_console(buf)

        tool_result = json.dumps({"status": "not_found", "key": "missing"})
        hook.after_tool("recall_from_scratchpad", {"key": "missing"}, tool_result)

        output = buf.getvalue()
        assert "not found" in output
        assert "missing" in output


def _make_console(buf: StringIO):
    """Create a Rich Console that writes to a StringIO buffer."""
    from rich.console import Console

    return Console(file=buf, force_terminal=True, width=120)
