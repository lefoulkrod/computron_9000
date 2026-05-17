"""Tests for the context size estimator."""

from __future__ import annotations

import json

import pytest

from sdk.context._estimator import (
    _CHARS_PER_TOKEN,
    _PER_MESSAGE_OVERHEAD_CHARS,
    estimate_tokens,
)


@pytest.mark.unit
def test_empty_messages_returns_zero():
    assert estimate_tokens([]) == 0


@pytest.mark.unit
def test_single_message_counts_content_plus_overhead():
    content = "hello world"  # 11 chars
    [
        {"role": "user", "content": content},
    ]
    expected = (len(content) + _PER_MESSAGE_OVERHEAD_CHARS) // _CHARS_PER_TOKEN
    assert estimate_tokens([{"role": "user", "content": content}]) == expected


@pytest.mark.unit
def test_assistant_thinking_is_counted():
    msg = {"role": "assistant", "content": "ok", "thinking": "deliberating"}
    chars = len(msg["content"]) + len(msg["thinking"]) + _PER_MESSAGE_OVERHEAD_CHARS
    assert estimate_tokens([msg]) == chars // _CHARS_PER_TOKEN


@pytest.mark.unit
def test_tool_name_on_tool_result_is_counted():
    msg = {"role": "tool", "tool_name": "read_file", "content": "abc"}
    chars = len(msg["content"]) + len(msg["tool_name"]) + _PER_MESSAGE_OVERHEAD_CHARS
    assert estimate_tokens([msg]) == chars // _CHARS_PER_TOKEN


@pytest.mark.unit
def test_tool_calls_counted_via_json_dumps():
    args = {"path": "/etc/hosts", "mode": "r"}
    msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": "1", "function": {"name": "read_file", "arguments": args}},
        ],
    }
    arg_chars = len(json.dumps(args, default=str))
    name_chars = len("read_file")
    expected_chars = _PER_MESSAGE_OVERHEAD_CHARS + name_chars + arg_chars
    assert estimate_tokens([msg]) == expected_chars // _CHARS_PER_TOKEN


@pytest.mark.unit
def test_non_serializable_arguments_do_not_crash():
    class Weird:
        pass

    msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"function": {"name": "f", "arguments": {"x": Weird()}}},
        ],
    }
    # Just verify it returns an int without raising.
    assert isinstance(estimate_tokens([msg]), int)


@pytest.mark.unit
def test_missing_optional_fields_safely_skipped():
    # A bare assistant message with no thinking, no tool_calls.
    msg = {"role": "assistant", "content": "ok"}
    assert estimate_tokens([msg]) == (len("ok") + _PER_MESSAGE_OVERHEAD_CHARS) // _CHARS_PER_TOKEN


@pytest.mark.unit
def test_tools_add_to_estimate():
    def example(name: str) -> str:
        """Echo back.

        Args:
            name: The name.
        """
        return name

    base = estimate_tokens([{"role": "user", "content": "hi"}])
    with_tools = estimate_tokens([{"role": "user", "content": "hi"}], tools=[example])
    assert with_tools > base


@pytest.mark.unit
def test_empty_tools_list_matches_none():
    msgs = [{"role": "user", "content": "hi"}]
    assert estimate_tokens(msgs, tools=[]) == estimate_tokens(msgs, tools=None)


@pytest.mark.unit
def test_non_string_content_is_ignored():
    # If a content value isn't a string (defensive — shouldn't happen but
    # the estimator must not crash), the overhead is still counted.
    msg = {"role": "user", "content": None}
    assert estimate_tokens([msg]) == _PER_MESSAGE_OVERHEAD_CHARS // _CHARS_PER_TOKEN
