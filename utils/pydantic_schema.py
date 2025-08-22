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
import types
from typing import TYPE_CHECKING, Any, Union, get_args, get_origin

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from collections.abc import Mapping

from pydantic import BaseModel

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
            # Recurse on first non-None; this will trigger list branch if needed
            return _placeholder_for_type(non_none[0])
        return "string"

    # List / sequence generics
    if origin in (list, list[int].__class__):  # type: ignore[attr-defined]
        args = get_args(tp)
        inner = args[0] if args else str
        inner_placeholder = _placeholder_for_type(inner)
        if isinstance(inner_placeholder, str):
            return [inner_placeholder, "..."]
        return [inner_placeholder]

    # Nested model
    if isinstance(tp, type) and issubclass(tp, BaseModel):  # type: ignore[arg-type]
        return model_placeholder_shape(tp)

    # Primitive
    if isinstance(tp, type) and tp in _PRIMITIVE_PLACEHOLDERS:
        return _PRIMITIVE_PLACEHOLDERS[tp]

    return "string"


def model_placeholder_shape(model_cls: type[BaseModel]) -> dict[str, JSONValue]:
    """Produce ordered placeholder mapping for a model's fields.

    Deterministic ordering aligns with Pydantic's internal field definition ordering.
    """
    shape: dict[str, JSONValue] = {}
    for name, field in model_cls.model_fields.items():  # type: ignore[attr-defined]
        shape[name] = _placeholder_for_type(field.annotation)  # type: ignore[arg-type]
    return shape


def schema_summary(
    model_cls: type[BaseModel],
    overrides: Mapping[str, JSONValue] | None = None,
    *,
    sort_keys: bool = True,
    indent: int = 4,
) -> str:
    """Return JSON string of simplified placeholder structure for a model.

    Args:
        model_cls: Pydantic model class.
        overrides: Optional mapping of field -> literal value / replacement placeholder.
        sort_keys: Whether to sort keys for stable textual output.
        indent: JSON indentation width.

    Returns:
        JSON pretty-printed string.
    """
    shape = model_placeholder_shape(model_cls)
    if overrides:
        for k, v in overrides.items():
            if k in shape:
                shape[k] = v
    return json.dumps(shape, indent=indent, sort_keys=sort_keys)


__all__ = [
    "JSONValue",
    "model_placeholder_shape",
    "schema_summary",
]
