"""Helper utilities for normalizing tool results, preparing tool arguments, and executing tool calls."""

from __future__ import annotations

import inspect
import json
import logging
import types
from typing import TYPE_CHECKING, Any, Protocol, Union, get_args, get_origin, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

logger = logging.getLogger(__name__)

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


async def _execute_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    tools: list[Callable[..., Any]],
) -> str:
    """Resolve and execute a single tool call, returning the result as a string.

    Args:
        tool_name: The name of the tool function to call.
        arguments: The arguments to pass to the tool function.
        tools: Available tool functions to match against.

    Returns:
        Plain string result for the LLM to read.
    """
    from sdk.events import AgentEvent, ToolCallPayload, publish_event
    from sdk.turn._turn import StopRequestedError

    # Some models emit function names with Python call syntax, e.g.
    # "browse_page(full_page=True)" instead of "browse_page".  Strip the
    # trailing parenthesised portion and merge any kwargs into arguments.
    if tool_name and "(" in tool_name:
        base, _, rest = tool_name.partition("(")
        tool_name = base
        # Try to parse kwargs like "full_page=True" into arguments
        rest = rest.rstrip(")")
        if rest and not arguments:
            arguments = {}
            for part in rest.split(","):
                part = part.strip()
                if "=" in part:
                    k, _, v = part.partition("=")
                    # Coerce simple Python literals
                    v = v.strip()
                    if v in ("True", "true"):
                        arguments[k.strip()] = True
                    elif v in ("False", "false"):
                        arguments[k.strip()] = False
                    elif v.isdigit():
                        arguments[k.strip()] = int(v)
                    else:
                        arguments[k.strip()] = v.strip("\"'")

    try:
        publish_event(AgentEvent(payload=ToolCallPayload(type="tool_call", name=str(tool_name))))
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to publish tool_call event for tool '%s'", tool_name)

    tool_func = next(
        (t for t in tools if getattr(t, "__name__", None) == tool_name),
        None,
    )
    if not tool_func:
        logger.error("Tool '%s' not found in tools.", tool_name)
        return "Tool not found"

    try:
        validated_args = _prepare_tool_arguments(tool_func, arguments)
        if inspect.iscoroutinefunction(tool_func):
            result = await tool_func(**validated_args)
        else:
            result = tool_func(**validated_args)
        normalized = _normalize_tool_result(result)
        return str(normalized) if not isinstance(normalized, str) else normalized
    except StopRequestedError:
        raise
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        logger.exception("Argument validation failed for tool '%s'", tool_name)
        return f"Argument validation failed: {exc}"
    except Exception as exc:
        logger.exception("Error running tool '%s'", tool_name)
        return str(exc)


__all__ = ["_execute_tool_call", "_normalize_tool_result", "_prepare_tool_arguments"]
