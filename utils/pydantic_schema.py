r"""Utilities for generating simplified, LLM friendly JSON placeholders for Pydantic models.

Centralizes logic for producing *example oriented* JSON structures that are:

* Stable across runs (deterministic field ordering)
* Without "$ref", "anyOf", explicit null markers
* Symbolic scalar placeholders (string, number, boolean)
* Lists of scalars -> ["string", "..."]
* Lists of objects -> single example element: [{ ... }]
* Optional[T] collapsed to T

The output is intended purely for prompt / documentation usage - NOT a formal
validation schema. Formal JSON Schemas can still be obtained via
`BaseModel.model_json_schema()` when needed.

Example:
    >>> from pydantic import BaseModel
    >>> class User(BaseModel):
    ...     id: int
    ...     name: str
    ...     tags: list[str]
    ...     notes: list[dict[str, str]] | None
    ...
    >>> from utils.pydantic_schema import model_placeholder_shape, schema_summary
    >>> schema_summary(User)
    '{\n    "id": "number", ... }'  # shortened example

Override:
    schema_summary(User, overrides={"id": 123, "name": "Alice"})

Targeted overrides inject concrete example literals without losing automatic
synchronization when fields are added or removed.
"""

from __future__ import annotations

import json
import re
import textwrap
import types
from typing import TYPE_CHECKING, Any, Union, get_args, get_origin

from pydantic import BaseModel

if TYPE_CHECKING:  # pragma: no cover - for typing only
    from collections.abc import Callable, Mapping

# Public re-export friendly alias used by agents for type hints
JSONValue = str | int | float | bool | dict[str, "JSONValue"] | list["JSONValue"] | None

_PRIMITIVE_PLACEHOLDERS: dict[type[Any], str] = {
    str: "string",
    int: "number",
    float: "number",
    bool: "boolean",
}


def _placeholder_for_type(tp: object) -> JSONValue:
    """Return placeholder representation for a Python / Pydantic type annotation.

    Rules:
        * Scalars -> symbolic string (string, number, boolean)
        * Lists of scalars -> ["string", "..."] pattern
        * Lists of objects -> single example element [{...}]
        * Optional[T] / Union[None, T] -> treat as T
        * BaseModel subclasses -> dict of field placeholders
    """
    origin = get_origin(tp)

    # Optional / Union - choose first non-None argument (handle Optional[list[T]])
    if origin in (Union, types.UnionType):  # type: ignore[arg-type]
        non_none = [a for a in get_args(tp) if a is not type(None)]
        if non_none:
            return _placeholder_for_type(non_none[0])
        return "string"

    # List / sequence generics
    if origin in (list, list[int].__class__):  # type: ignore[attr-defined]
        args = get_args(tp)
        inner = args[0] if args else str
        # Lists of objects -> single example element [{...}]
        if isinstance(inner, type) and issubclass(inner, BaseModel):
            return [model_placeholder_shape(inner)]
        # Lists of scalars -> pattern [placeholder, "..."]
        scalar = (
            _PRIMITIVE_PLACEHOLDERS[inner]
            if isinstance(inner, type) and inner in _PRIMITIVE_PLACEHOLDERS
            else "string"
        )
        return [scalar, "..."]

    # Pydantic model -> dict of field placeholders
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        return model_placeholder_shape(tp)

    # Scalars
    if isinstance(tp, type) and tp in _PRIMITIVE_PLACEHOLDERS:
        return _PRIMITIVE_PLACEHOLDERS[tp]
    return "string"


def _extract_field_docs_from_docstring(
    model_cls: type[BaseModel], *, allowed_fields: set[str]
) -> dict[str, str]:
    """Parse Google-style "Args:" section from a model class docstring.

    Extracts a mapping of field name -> description for names present in
    allowed_fields. Ignores unknown names. Handles multiline descriptions.

    Args:
        model_cls: The Pydantic model class whose docstring to parse.
        allowed_fields: Set of field names to include in the result.

    Returns:
        Dict of field documentation. Empty if no appropriate docstring/section.
    """
    doc = getattr(model_cls, "__doc__", None)
    if not doc:
        return {}
    doc = textwrap.dedent(doc)
    lines = doc.splitlines()
    # Find the Args or Arguments section header (allow indentation)
    args_header_indices: list[int] = []
    args_header_pattern = re.compile(r"^\s*(Args|Arguments):\s*$")
    for i, line in enumerate(lines):
        if args_header_pattern.match(line):
            args_header_indices.append(i)
    if not args_header_indices:
        return {}

    # We'll parse only the first Args section found
    start = args_header_indices[0] + 1
    # Section ends when a new top-level section header appears or EOF
    section_end = len(lines)
    section_headers = (
        "Returns",
        "Raises",
        "Examples",
        "Attributes",
        "Notes",
        "References",
        "See Also",
        "Warnings",
    )
    section_header_pattern = re.compile(r"^\s*(" + "|".join(section_headers) + r"):\s*$")
    for j in range(start, len(lines)):
        # A new section header is non-indented and matches known headers
        if not lines[j].startswith((" ", "\t")) and section_header_pattern.match(lines[j].strip()):
            section_end = j
            break

    # Parse args block: expect indented entries like "name: description"
    entries: dict[str, str] = {}
    current_name: str | None = None
    current_desc_parts: list[str] = []

    def _flush_current() -> None:
        nonlocal current_name, current_desc_parts
        if current_name and current_name in allowed_fields:
            desc = " ".join(s.strip() for s in current_desc_parts if s.strip())
            if desc:
                entries[current_name] = desc
        current_name = None
        current_desc_parts = []

    for raw in lines[start:section_end]:
        if not raw.strip():
            # Blank line inside args; treat as paragraph break
            if current_name is not None:
                current_desc_parts.append("")
            continue
        line = raw.lstrip()
        if ":" in line and re.match(r"^[A-Za-z_][A-Za-z0-9_\-]*\s*:\s*", line):
            # New entry
            _flush_current()
            name, rest = line.split(":", 1)
            current_name = name.strip()
            current_desc_parts = [rest.strip()]
        elif current_name is not None:
            # Continuation of previous description
            current_desc_parts.append(line.strip())

    _flush_current()
    return entries


def _unwrap_optional(tp: object) -> object:
    """Return the underlying type for Optional/Union[None, T] annotations."""
    origin = get_origin(tp)
    if origin in (Union, types.UnionType):  # type: ignore[arg-type]
        non_none = [a for a in get_args(tp) if a is not type(None)]
        if non_none:
            return non_none[0]
    return tp


def _is_list_of(tp: object, item_predicate: Callable[[object], bool]) -> tuple[bool, object | None]:
    origin = get_origin(tp)
    if origin in (list, list[int].__class__):  # type: ignore[attr-defined]
        args = get_args(tp)
        inner = args[0] if args else str
        return bool(item_predicate(inner)), inner
    return False, None


def _build_shape_and_docs(
    model_cls: type[BaseModel], path: tuple[str, ...] = ()
) -> tuple[dict[str, JSONValue], dict[tuple[str, ...], dict[str, str]]]:
    """Recursively build placeholder shape and a map of field docs at each object path."""
    shape: dict[str, JSONValue] = {}
    docs_map: dict[tuple[str, ...], dict[str, str]] = {}

    # Field docs at this level
    field_names = set(model_cls.model_fields.keys())  # type: ignore[attr-defined]
    field_docs = _extract_field_docs_from_docstring(model_cls, allowed_fields=field_names)

    for name, field in model_cls.model_fields.items():  # type: ignore[attr-defined]
        ann = _unwrap_optional(field.annotation)
        # List handling
        is_list, inner = _is_list_of(
            ann,
            lambda t: isinstance(t, type) and issubclass(t, BaseModel),
        )
        if is_list and isinstance(inner, type) and issubclass(inner, BaseModel):
            nested_shape, nested_docs = _build_shape_and_docs(inner, (*path, name))
            shape[name] = [nested_shape]
            docs_map.update(nested_docs)
            continue

        # Nested model
        if isinstance(ann, type) and issubclass(ann, BaseModel):
            nested_shape, nested_docs = _build_shape_and_docs(ann, (*path, name))
            shape[name] = nested_shape
            docs_map.update(nested_docs)
            continue

        # Fallback to existing placeholder logic for primitives and lists of primitives
        shape[name] = _placeholder_for_type(ann)

    # Record docs for this path (only include docs for keys present)
    if field_docs:
        docs_map[path] = {k: v for k, v in field_docs.items() if k in shape}
    return shape, docs_map


def _render_commented_json(
    obj: JSONValue,
    docs_map: dict[tuple[str, ...], dict[str, str]],
    *,
    indent: int,
    sort_keys: bool,
) -> str:
    """Render a JSON-like string from obj, inserting // comments using docs_map.

    Comments are inserted above keys for object at the corresponding path.
    """

    def render_value(value: JSONValue, path: tuple[str, ...], level: int) -> list[str]:
        if isinstance(value, dict):
            return render_dict(value, path, level)
        if isinstance(value, list):
            return render_list(value, path, level)
        # Scalars always rendered with json.dumps for correctness
        return ["".join((" " * (indent * level), json.dumps(value)))]

    def render_dict(d: dict[str, JSONValue], path: tuple[str, ...], level: int) -> list[str]:
        lines: list[str] = []
        pad = " " * (indent * level)
        lines.append(pad + "{")
        items = list(d.items())
        if sort_keys:
            items.sort(key=lambda kv: kv[0])
        field_docs = docs_map.get(path, {})
        for i, (k, v) in enumerate(items):
            last = i == len(items) - 1
            key_pad = " " * (indent * (level + 1))
            doc = field_docs.get(k)
            if doc:
                lines.append(key_pad + "// " + doc)
            if isinstance(v, dict):
                child_lines = render_dict(v, (*path, k), level + 1)
                # Attach first child line to key prefix
                first = child_lines[0]
                rest = child_lines[1:]
                lines.append(key_pad + json.dumps(k) + ": " + first.strip())
                lines.extend(rest)
                if not last:
                    lines[-1] = lines[-1] + ","
            elif isinstance(v, list):
                child_lines = render_list(v, (*path, k), level + 1)
                lines.append(key_pad + json.dumps(k) + ": " + child_lines[0].strip())
                lines.extend(child_lines[1:])
                if not last:
                    lines[-1] = lines[-1] + ","
            else:
                line = key_pad + json.dumps(k) + ": " + json.dumps(v)
                if not last:
                    line += ","
                lines.append(line)
        lines.append(pad + "}")
        return lines

    def render_list(lst: list[JSONValue], path: tuple[str, ...], level: int) -> list[str]:
        lines: list[str] = []
        pad = " " * (indent * level)
        lines.append(pad + "[")
        for idx, el in enumerate(lst):
            last = idx == len(lst) - 1
            child_lines = render_value(el, path, level + 1)
            lines.extend(child_lines)
            if not last:
                lines[-1] = lines[-1] + ","
        lines.append(pad + "]")
        return lines

    return "\n".join(render_value(obj, (), 0))


def model_placeholder_shape(model_cls: type[BaseModel]) -> dict[str, JSONValue]:
    """Return a simplified placeholder shape for a Pydantic model.

    - Deterministic field order (by declaration order; JSON render can sort later)
    - Optional[T] collapsed to T
    - Lists of scalars -> [placeholder, "..."]
    - Lists of models -> single example element [{...}]
    """
    shape: dict[str, JSONValue] = {}
    for name, field in model_cls.model_fields.items():  # type: ignore[attr-defined]
        ann = _unwrap_optional(field.annotation)
        origin = get_origin(ann)
        if origin in (list, list[int].__class__):  # type: ignore[attr-defined]
            args = get_args(ann)
            inner = args[0] if args else str
            if isinstance(inner, type) and issubclass(inner, BaseModel):
                shape[name] = [model_placeholder_shape(inner)]
            else:
                shape[name] = [_PRIMITIVE_PLACEHOLDERS.get(inner, "string"), "..."]
            continue

        if isinstance(ann, type) and issubclass(ann, BaseModel):
            shape[name] = model_placeholder_shape(ann)
            continue

        shape[name] = _placeholder_for_type(ann)
    return shape


def schema_summary(
    model_cls: type[BaseModel],
    overrides: Mapping[str, JSONValue] | None = None,
    *,
    indent: int = 4,
    sort_keys: bool = False,
    include_docs: bool = False,
) -> str:
    """Return a JSON example string for the model, with optional comments.

    - Applies top-level overrides to replace placeholders
    - When include_docs=True, parses Google-style Args docs from model and nested
      models and renders them as // comments above the corresponding keys.
    """
    # Build base shape
    if include_docs:
        shape, docs_map = _build_shape_and_docs(model_cls)
    else:
        shape = model_placeholder_shape(model_cls)
        docs_map = {}

    # Apply top-level overrides (do not traverse into nested objects)
    if overrides:
        for k, v in overrides.items():
            if k in shape:
                shape[k] = v

    if not include_docs:
        return json.dumps(shape, indent=indent, sort_keys=sort_keys)

    # Render with comments for both top-level and nested objects
    return _render_commented_json(shape, docs_map, indent=indent, sort_keys=sort_keys)


__all__ = [
    "JSONValue",
    "model_placeholder_shape",
    "schema_summary",
]
