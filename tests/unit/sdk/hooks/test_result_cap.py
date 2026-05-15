"""Tests for ToolResultCapHook — caps oversized tool results."""

import pytest

from sdk.hooks._result_cap import ToolResultCapHook, _CHARS_PER_TOKEN


@pytest.fixture()
def hook():
    """Hook with a 100-token context window (400 char limit)."""
    return ToolResultCapHook(context_window=100)


def test_short_result_passes_through(hook):
    result = hook.after_tool("read_file", {}, "hello")
    assert result == "hello"


def test_result_at_exact_limit_passes_through(hook):
    text = "x" * (100 * _CHARS_PER_TOKEN)
    result = hook.after_tool("read_file", {}, text)
    assert result == text


def test_result_one_over_limit_is_replaced(hook):
    text = "x" * (100 * _CHARS_PER_TOKEN + 1)
    result = hook.after_tool("read_file", {}, text)
    assert result.startswith("Error: tool result too large")
    assert "401" in result
    assert "400" in result


def test_error_message_includes_tool_guidance(hook):
    text = "x" * 1000
    result = hook.after_tool("grep", {}, text)
    assert "more targeted request" in result


def test_non_string_result_passes_through(hook):
    result = hook.after_tool("some_tool", {}, 42)
    assert result == 42


def test_empty_string_passes_through(hook):
    result = hook.after_tool("read_file", {}, "")
    assert result == ""


def test_zero_ctx_means_zero_limit():
    hook = ToolResultCapHook(context_window=0)
    result = hook.after_tool("read_file", {}, "any text")
    assert result.startswith("Error: tool result too large")


def test_large_ctx_allows_large_results():
    hook = ToolResultCapHook(context_window=128_000)
    text = "x" * 500_000
    result = hook.after_tool("read_file", {}, text)
    assert result == text
