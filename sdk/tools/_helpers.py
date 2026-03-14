"""Helper utilities for normalizing tool results and preparing tool arguments."""

from __future__ import annotations

import inspect
import json
import types
from typing import TYPE_CHECKING, Any, Protocol, Union, get_args, get_origin, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

from pydantic import BaseModel

# Strings the LLM commonly sends for boolean values.
_BOOL_TRUE = frozenset({"true", "1", "yes"})
_BOOL_FALSE = frozenset({"false", "0", "no"})


@runtime_checkable
class _HasDict(Protocol):
    def dict(self) -> Mapping[str, object]:  # pragma: no cover - protocol
        ...


def _normalize_tool_result(obj: object) -> object:
    """Prepare tool results for JSON serialization by normalizing nested models."""
    if isinstance(obj, BaseModel):
        return _normalize_tool_result(obj.model_dump())
    if isinstance(obj, _HasDict):
        return _normalize_tool_result(obj.dict())
    if isinstance(obj, dict):
        return {k: _normalize_tool_result(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple | set):
        return [_normalize_tool_result(i) for i in obj]
    return obj


def _unwrap_optional(tp: object) -> object:
    """Strip ``Optional`` / ``X | None`` wrappers, returning the inner type.

    Returns the original type unchanged if it is not an optional union.
    """
    origin = get_origin(tp)
    if origin in (Union, types.UnionType):
        non_none = [a for a in get_args(tp) if a is not type(None)]
        # Only unwrap simple Optional[T] (one non-None member).
        if len(non_none) == 1:
            return non_none[0]
    return tp


def _coerce_bool(value: Any) -> bool:
    """Convert LLM string representations to bool correctly."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in _BOOL_TRUE:
            return True
        if low in _BOOL_FALSE:
            return False
        msg = f"Cannot convert {value!r} to bool"
        raise ValueError(msg)
    return bool(value)


def _validate_pydantic(model_type: type, value: Any) -> Any:
    """JSON-parse (if string) then validate via Pydantic v2/v1."""
    if isinstance(value, str):
        value = json.loads(value)
    if hasattr(model_type, "model_validate"):
        return model_type.model_validate(value)
    if hasattr(model_type, "parse_obj"):
        return model_type.parse_obj(value)
    return value


def _is_pydantic(tp: object) -> bool:
    return isinstance(tp, type) and (
        hasattr(tp, "model_validate") or hasattr(tp, "parse_obj")
    )


def _coerce_value(expected_type: Any, value: Any) -> Any:
    """Coerce a single *value* to *expected_type*."""
    # Unwrap Optional[T] / T | None so we dispatch on T.
    unwrapped = _unwrap_optional(expected_type)

    # None passthrough — if the value is None and the original type was
    # optional, just let it through.
    if value is None and unwrapped is not expected_type:
        return None

    origin = get_origin(unwrapped)

    # list[T] — coerce each element when the item type is known.
    if origin is list:
        args = get_args(unwrapped)
        item_type = args[0] if args else None
        if not isinstance(value, list):
            return value
        if item_type is None:
            return value
        return [_coerce_value(item_type, item) for item in value]

    # Pydantic model
    if _is_pydantic(unwrapped):
        return _validate_pydantic(unwrapped, value)

    # Scalar primitives
    if unwrapped is bool:
        return _coerce_bool(value)
    if unwrapped is int:
        return int(value)
    if unwrapped is float:
        return float(value)
    if unwrapped is str:
        return str(value)

    return value


def _prepare_tool_arguments(
    tool_func: Callable[..., Any], arguments: dict[str, Any]
) -> dict[str, Any]:
    """Prepare tool function arguments by validating and converting via type hints."""
    sig = inspect.signature(tool_func, eval_str=True)
    func_name = getattr(tool_func, "__name__", repr(tool_func))
    validated: dict[str, Any] = {}

    for name, param in sig.parameters.items():
        value = arguments.get(name, param.default)

        if value is inspect.Parameter.empty:
            msg = f"Required parameter '{name}' is missing for tool '{func_name}'"
            raise ValueError(msg)

        annotation = param.annotation
        if annotation is inspect.Parameter.empty:
            validated[name] = value
        else:
            validated[name] = _coerce_value(annotation, value)

    return validated


__all__ = ["_normalize_tool_result", "_prepare_tool_arguments"]
