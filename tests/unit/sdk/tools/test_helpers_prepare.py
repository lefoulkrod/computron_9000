"""Tests for the _prepare_tool_arguments helper."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from sdk.tools import _prepare_tool_arguments


class _Item(BaseModel):
    """Simple Pydantic model for tests."""

    name: str
    value: int


class _Node(BaseModel):
    """Self-referencing model for tree tests."""

    label: str
    children: list[_Node] = []


# ── Scalar coercion ─────────────────────────────────────────────────


@pytest.mark.unit
def test_basic_type_coercion():
    """Strings from the LLM are coerced to the annotated scalar types."""

    def tool(name: str, count: int, price: float) -> str: ...

    result = _prepare_tool_arguments(tool, {
        "name": "test",
        "count": "42",
        "price": "19.99",
    })

    assert result == {"name": "test", "count": 42, "price": 19.99}
    assert isinstance(result["count"], int)
    assert isinstance(result["price"], float)


@pytest.mark.unit
def test_bool_coercion_true_variants():
    """LLM boolean strings like 'true', '1', 'yes' coerce to True."""

    def tool(flag: bool) -> str: ...

    for truthy in ("true", "True", "TRUE", "1", "yes", "Yes"):
        result = _prepare_tool_arguments(tool, {"flag": truthy})
        assert result["flag"] is True, f"{truthy!r} should be True"


@pytest.mark.unit
def test_bool_coercion_false_variants():
    """LLM boolean strings like 'false', '0', 'no' coerce to False."""

    def tool(flag: bool) -> str: ...

    for falsy in ("false", "False", "FALSE", "0", "no", "No"):
        result = _prepare_tool_arguments(tool, {"flag": falsy})
        assert result["flag"] is False, f"{falsy!r} should be False"


@pytest.mark.unit
def test_bool_coercion_native_values():
    """Native bools and int 0/1 pass through correctly."""

    def tool(flag: bool) -> str: ...

    assert _prepare_tool_arguments(tool, {"flag": True})["flag"] is True
    assert _prepare_tool_arguments(tool, {"flag": False})["flag"] is False
    assert _prepare_tool_arguments(tool, {"flag": 0})["flag"] is False
    assert _prepare_tool_arguments(tool, {"flag": 1})["flag"] is True


@pytest.mark.unit
def test_bool_coercion_invalid_string():
    """An unrecognised string for a bool parameter raises ValueError."""

    def tool(flag: bool) -> str: ...

    with pytest.raises(ValueError, match="Cannot convert"):
        _prepare_tool_arguments(tool, {"flag": "maybe"})


# ── Optional / None handling ────────────────────────────────────────


@pytest.mark.unit
def test_optional_none_passthrough():
    """None values pass through for Optional parameters."""

    def tool(name: str, tag: str | None = None) -> str: ...

    result = _prepare_tool_arguments(tool, {"name": "x", "tag": None})
    assert result["tag"] is None


@pytest.mark.unit
def test_optional_with_value_coerces():
    """Optional[int] with a non-None string value still coerces to int."""

    def tool(count: int | None = None) -> str: ...

    result = _prepare_tool_arguments(tool, {"count": "7"})
    assert result["count"] == 7
    assert isinstance(result["count"], int)


# ── Defaults and missing params ─────────────────────────────────────


@pytest.mark.unit
def test_defaults_used_when_absent():
    """Parameters with defaults use those defaults when not supplied."""

    def tool(name: str, count: int = 10, active: bool = False) -> str: ...

    result = _prepare_tool_arguments(tool, {"name": "test"})
    assert result == {"name": "test", "count": 10, "active": False}


@pytest.mark.unit
def test_missing_required_param_raises():
    """A missing required parameter raises ValueError with tool name."""

    def my_tool(name: str, count: int) -> str: ...

    with pytest.raises(ValueError, match="'count'.*'my_tool'"):
        _prepare_tool_arguments(my_tool, {"name": "test"})


@pytest.mark.unit
def test_no_type_hints_passthrough():
    """Parameters without type hints pass through unchanged."""

    def tool(name, count):
        ...

    result = _prepare_tool_arguments(tool, {"name": "test", "count": 42})
    assert result == {"name": "test", "count": 42}


# ── Pydantic model coercion ─────────────────────────────────────────


@pytest.mark.unit
def test_pydantic_from_dict():
    """A dict is validated into a Pydantic model."""

    def tool(item: _Item) -> str: ...

    result = _prepare_tool_arguments(tool, {
        "item": {"name": "test", "value": 42},
    })
    assert isinstance(result["item"], _Item)
    assert result["item"].name == "test"
    assert result["item"].value == 42


@pytest.mark.unit
def test_pydantic_from_json_string():
    """A JSON string is parsed and validated into a Pydantic model."""

    def tool(item: _Item) -> str: ...

    result = _prepare_tool_arguments(tool, {
        "item": '{"name": "test", "value": 42}',
    })
    assert isinstance(result["item"], _Item)


@pytest.mark.unit
def test_pydantic_invalid_json_raises():
    """Invalid JSON for a Pydantic param raises JSONDecodeError."""

    def tool(item: _Item) -> str: ...

    with pytest.raises(json.JSONDecodeError):
        _prepare_tool_arguments(tool, {"item": "not json"})


# ── List coercion ───────────────────────────────────────────────────


@pytest.mark.unit
def test_list_of_pydantic_from_dicts():
    """list[Model] items are validated individually."""

    def tool(items: list[_Item]) -> str: ...

    result = _prepare_tool_arguments(tool, {
        "items": [
            {"name": "a", "value": 1},
            {"name": "b", "value": 2},
        ],
    })
    assert len(result["items"]) == 2
    assert all(isinstance(i, _Item) for i in result["items"])


@pytest.mark.unit
def test_list_of_pydantic_from_json_strings():
    """list[Model] items given as JSON strings are parsed then validated."""

    def tool(items: list[_Item]) -> str: ...

    result = _prepare_tool_arguments(tool, {
        "items": ['{"name": "a", "value": 1}', '{"name": "b", "value": 2}'],
    })
    assert len(result["items"]) == 2
    assert all(isinstance(i, _Item) for i in result["items"])


@pytest.mark.unit
def test_list_of_int_coerces_items():
    """list[int] items are individually coerced from strings."""

    def tool(nums: list[int]) -> str: ...

    result = _prepare_tool_arguments(tool, {"nums": ["1", "2", "3"]})
    assert result["nums"] == [1, 2, 3]
    assert all(isinstance(n, int) for n in result["nums"])


@pytest.mark.unit
def test_list_of_str_passthrough():
    """list[str] items pass through unchanged."""

    def tool(tags: list[str]) -> str: ...

    result = _prepare_tool_arguments(tool, {
        "tags": ["alpha", "beta"],
    })
    assert result["tags"] == ["alpha", "beta"]


@pytest.mark.unit
def test_empty_list_passthrough():
    """Empty lists pass through regardless of item type."""

    def tool(items: list[_Item]) -> str: ...

    result = _prepare_tool_arguments(tool, {"items": []})
    assert result["items"] == []


@pytest.mark.unit
def test_bare_list_passthrough():
    """Bare `list` (no type arg) passes through without coercion."""

    def tool(items: list) -> str: ...

    result = _prepare_tool_arguments(tool, {"items": [1, "two", 3.0]})
    assert result["items"] == [1, "two", 3.0]


# ── Optional list ───────────────────────────────────────────────────


@pytest.mark.unit
def test_optional_list_of_int():
    """Optional[list[int]] unwraps optional then coerces items."""

    def tool(nums: list[int] | None = None) -> str: ...

    result = _prepare_tool_arguments(tool, {"nums": ["4", "5"]})
    assert result["nums"] == [4, 5]

    result = _prepare_tool_arguments(tool, {"nums": None})
    assert result["nums"] is None


# ── Type conversion errors ──────────────────────────────────────────


@pytest.mark.unit
def test_int_conversion_error():
    """Non-numeric string for int param raises ValueError."""

    def tool(count: int) -> str: ...

    with pytest.raises(ValueError):
        _prepare_tool_arguments(tool, {"count": "not_a_number"})


# ── Self-referencing models ─────────────────────────────────────────


@pytest.mark.unit
def test_self_referencing_pydantic_model():
    """Nested self-referencing Pydantic models are validated recursively."""

    def tool(root: _Node) -> str: ...

    result = _prepare_tool_arguments(tool, {
        "root": {
            "label": "parent",
            "children": [
                {"label": "child", "children": []},
            ],
        },
    })
    assert isinstance(result["root"], _Node)
    assert result["root"].label == "parent"
    assert len(result["root"].children) == 1
    assert isinstance(result["root"].children[0], _Node)
