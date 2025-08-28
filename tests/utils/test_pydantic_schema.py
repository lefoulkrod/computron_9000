"""Unit tests for utils.pydantic_schema simplified placeholder generation.

Covers:
* Primitive field placeholder mapping
* List of primitives vs list of objects behavior
* Optional field collapsing
* Nested model shape production
* Override injection in schema_summary
"""
from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from utils.pydantic_schema import model_placeholder_shape, schema_summary


class Inner(BaseModel):
    name: str
    count: int


class Outer(BaseModel):
    id: int
    title: str | None
    tags: list[str]
    inners: list[Inner]
    optional_list: list[int] | None = None


@pytest.mark.unit
def test_model_placeholder_shape_primitives() -> None:
    """Primitives mapped to symbolic tokens and list patterns."""
    shape = model_placeholder_shape(Outer)
    assert shape["id"] == "number"
    assert shape["title"] == "string"  # Optional collapsed
    assert shape["tags"] == ["string", "..."]


@pytest.mark.unit
def test_model_placeholder_shape_nested() -> None:
    """Nested model list yields single element example object."""
    shape = model_placeholder_shape(Outer)
    inners = shape["inners"]
    assert isinstance(inners, list)
    assert len(inners) == 1
    inner_obj = inners[0]
    assert inner_obj == {"name": "string", "count": "number"}


@pytest.mark.unit
def test_optional_list_collapses_type() -> None:
    """Optional list treated as underlying list type placeholder."""
    shape = model_placeholder_shape(Outer)
    assert shape["optional_list"] == ["number", "..."]


@pytest.mark.unit
def test_schema_summary_overrides() -> None:
    """Overrides replace placeholder values when field present."""
    s = schema_summary(Outer, overrides={"id": 123, "title": "Example"}, sort_keys=True)
    data = json.loads(s)
    assert data["id"] == 123
    assert data["title"] == "Example"
    # Un-overridden field still placeholder
    assert data["tags"] == ["string", "..."]


@pytest.mark.unit
def test_schema_summary_hardcoded_json_match() -> None:
    """Schema summary matches an expected hardcoded JSON string (sorted keys).

    Ensures deterministic formatting for downstream prompt embedding stability.
    """
    expected = (
        '{\n'
        '"id": "number",\n'
        '"inners": [\n'
        '{\n'
        '"count": "number",\n'
        '"name": "string"\n'
        '}\n'
        '],\n'
        '"optional_list": [\n'
        '"number",\n'
        '"..."\n'
        '],\n'
        '"tags": [\n'
        '"string",\n'
        '"..."\n'
        '],\n'
        '"title": "string"\n'
        '}'
    )
    produced = schema_summary(Outer, sort_keys=True, overrides=None, indent=0)
    assert produced == expected
