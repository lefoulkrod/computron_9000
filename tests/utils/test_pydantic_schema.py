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
    """Inner container model.

    Args:
        name: A name string.
        count: A count value.
    """

    name: str
    count: int


class Outer(BaseModel):
    """Outer container model.

    Args:
        id: Numeric identifier.
        title: Optional title value.
        tags: List of tag strings.
        inners: List of Inner objects.
        optional_list: Optional list of integers.
    """

    id: int
    title: str | None
    tags: list[str]
    inners: list[Inner]
    optional_list: list[int] | None = None


def _strip_json_comments(s: str) -> str:
    """Remove lines that are // comments to allow json.loads on commented examples."""
    return "\n".join(line for line in s.splitlines() if not line.lstrip().startswith("//"))


class DocumentedModel(BaseModel):
    """A model with Google-style Args in the docstring.

    Args:
        id: Unique identifier for the entity.
        name: Human-readable name (no PII).
        tags: Optional labels for grouping. Multiple allowed.
        inner: Nested object with details.

    Returns:
        Not relevant for models, present to mark end of Args section.
    """

    id: int
    name: str
    tags: list[str]
    inner: Inner


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
    s = schema_summary(
        Outer, overrides={"id": 123, "title": "Example"}, sort_keys=True, include_docs=True
    )
    # Comments are not valid JSON; strip them before parsing
    data = json.loads(_strip_json_comments(s))
    assert data["id"] == 123
    assert data["title"] == "Example"
    # Un-overridden field still placeholder
    assert data["tags"] == ["string", "..."]
    # And we also included docs as comments above top-level keys
    assert "// Numeric identifier." in s
    assert "// Optional title value." in s


@pytest.mark.unit
def test_schema_summary_hardcoded_json_match() -> None:
    """Schema summary matches an expected hardcoded JSON string (sorted keys).

    Ensures deterministic formatting for downstream prompt embedding stability.
    """
    expected = (
        '{\n'
        '// Numeric identifier.\n'
        '"id": "number",\n'
        '// List of Inner objects.\n'
        '"inners": [\n'
    '{\n'
    '// A count value.\n'
    '"count": "number",\n'
    '// A name string.\n'
    '"name": "string"\n'
    '}\n'
        '],\n'
        '// Optional list of integers.\n'
        '"optional_list": [\n'
        '"number",\n'
        '"..."\n'
        '],\n'
        '// List of tag strings.\n'
        '"tags": [\n'
        '"string",\n'
        '"..."\n'
        '],\n'
        '// Optional title value.\n'
        '"title": "string"\n'
        '}'
    )
    produced = schema_summary(Outer, sort_keys=True, overrides=None, indent=0, include_docs=True)
    # With include_docs=True, comments should be present inline and match expected exactly
    assert produced == expected


@pytest.mark.unit
def test_schema_summary_no_docstring_model_has_no_comments() -> None:
    """Models without docstrings should not render comments even with include_docs=True."""

    class NoDocModel(BaseModel):
        a: int
        b: str

    s = schema_summary(NoDocModel, include_docs=True, sort_keys=True)
    assert "//" not in s
    # And content parses fine as JSON
    json.loads(_strip_json_comments(s))


@pytest.mark.unit
def test_schema_summary_other_docstyles_are_ignored() -> None:
    """NumPy and Sphinx/ReST docstring styles should be ignored by the Args parser."""

    class NumpyDocModel(BaseModel):
        """Example using NumPy docstring style.

        Parameters
        ----------
        x : int
            An integer value.
        y : str
            A string value.
        """

        x: int
        y: str

    class SphinxDocModel(BaseModel):
        """Example using Sphinx/ReST docstring style.

        :param p: Parameter p.
        :type p: int
        :param q: Parameter q.
        :type q: str
        """

        p: int
        q: str

    s1 = schema_summary(NumpyDocModel, include_docs=True, sort_keys=True)
    s2 = schema_summary(SphinxDocModel, include_docs=True, sort_keys=True)
    assert "//" not in s1
    assert "//" not in s2


@pytest.mark.unit
def test_schema_summary_includes_docs_as_comments_when_enabled() -> None:
    """Docs are rendered as // comments above top-level keys when include_docs=True."""
    s = schema_summary(DocumentedModel, include_docs=True, sort_keys=True, indent=2)
    # Presence of comment lines for documented fields
    assert "// Unique identifier for the entity." in s
    assert "// Human-readable name (no PII)." in s
    assert "// Optional labels for grouping. Multiple allowed." in s
    assert "// Nested object with details." in s
    # Ensure comments precede the appropriate top-level keys (indent-aware)
    assert "  // Unique identifier for the entity.\n  \"id\":" in s
    assert "  // Human-readable name (no PII).\n  \"name\":" in s
    assert "  // Optional labels for grouping. Multiple allowed.\n  \"tags\":" in s
    assert "  // Nested object with details.\n  \"inner\":" in s


@pytest.mark.unit
def test_schema_summary_no_docs_by_default() -> None:
    """Docs are not included unless explicitly requested (no // comments)."""
    s = schema_summary(DocumentedModel, sort_keys=True)
    assert "// Unique identifier for the entity." not in s
