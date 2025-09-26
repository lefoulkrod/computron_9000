"""Tests for the tool loop functionality."""

import pytest
from pydantic import BaseModel

from agents.ollama.sdk.tool_loop import _normalize_tool_result


class DummyModel(BaseModel):
    x: int
    y: str


class NestedModel(BaseModel):
    a: DummyModel
    b: list[DummyModel]
    c: dict[str, DummyModel]


@pytest.mark.unit
def test_normalize_tool_result_with_pydantic_model():
    """
    Test that _normalize_tool_result correctly converts a Pydantic model to a dict.
    """
    model = DummyModel(x=1, y="foo")
    result = _normalize_tool_result(model)
    assert isinstance(result, dict)
    assert result == {"x": 1, "y": "foo"}


@pytest.mark.unit
def test_normalize_tool_result_with_nested_structures():
    """
    Test that _normalize_tool_result recursively converts nested Pydantic models in lists and dicts.
    """
    nested = NestedModel(
        a=DummyModel(x=2, y="bar"),
        b=[DummyModel(x=3, y="baz")],
        c={"k": DummyModel(x=4, y="qux")},
    )
    result = _normalize_tool_result(nested)
    assert isinstance(result, dict)
    assert result["a"] == {"x": 2, "y": "bar"}
    assert result["b"] == [{"x": 3, "y": "baz"}]
    assert result["c"] == {"k": {"x": 4, "y": "qux"}}


@pytest.mark.unit
def test_normalize_tool_result_with_primitive_types():
    """
    Test that _normalize_tool_result returns primitive types unchanged.
    """
    assert _normalize_tool_result(42) == 42
    assert _normalize_tool_result("hello") == "hello"
    assert _normalize_tool_result([1, 2, 3]) == [1, 2, 3]
    assert _normalize_tool_result({"a": 1}) == {"a": 1}


@pytest.mark.unit
def test_normalize_tool_result_with_non_pydantic_object():
    """
    Test that _normalize_tool_result falls back to the object itself for unsupported types.
    """

    class NotSerializable:
        pass

    obj = NotSerializable()
    assert _normalize_tool_result(obj) == obj
