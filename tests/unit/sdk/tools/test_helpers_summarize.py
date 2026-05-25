"""Tests for the _summarize_arguments helper."""

from __future__ import annotations

import pytest

from sdk.tools import _summarize_arguments


@pytest.mark.unit
def test_string_values_pass_through():
    out = _summarize_arguments({"filename": "src/app.py"})
    assert out == {"filename": "src/app.py"}


@pytest.mark.unit
def test_non_string_values_are_json_stringified():
    out = _summarize_arguments({"count": 3, "deep": True, "opts": {"a": 1}})
    assert out == {"count": "3", "deep": "true", "opts": '{"a": 1}'}


@pytest.mark.unit
def test_long_values_are_truncated():
    out = _summarize_arguments({"content": "x" * 5000})
    assert len(out["content"]) == 64
    assert out["content"].endswith("…")


@pytest.mark.unit
def test_whitespace_is_collapsed_to_one_line():
    out = _summarize_arguments({"content": "line one\n\n  line two\ttabbed"})
    assert out["content"] == "line one line two tabbed"


@pytest.mark.unit
def test_keys_are_coerced_to_strings():
    out = _summarize_arguments({1: "a"})
    assert out == {"1": "a"}


@pytest.mark.unit
def test_empty_arguments_give_empty_map():
    assert _summarize_arguments({}) == {}
