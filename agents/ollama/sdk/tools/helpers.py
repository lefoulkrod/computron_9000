"""Helper utilities for normalizing tool results and preparing tool arguments."""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


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


def _prepare_tool_arguments(
    tool_func: Callable[..., Any], arguments: dict[str, Any]
) -> dict[str, Any]:
    """Prepare tool function arguments by validating and converting via type hints."""
    validated_args = {}
    # Introspect the tool signature so we can coerce each supplied argument.
    sig = inspect.signature(tool_func)

    for arg_name, param in sig.parameters.items():
        expected_type = param.annotation
        value = arguments.get(arg_name, param.default)

        # Required parameters without a provided value should surface immediately.
        if value is inspect.Parameter.empty:
            msg = f"Required parameter '{arg_name}' is missing"
            raise ValueError(msg)

        if expected_type is not inspect.Parameter.empty:
            origin = getattr(expected_type, "__origin__", None)
            if origin is not None and origin is type(None):
                validated_args[arg_name] = value
            elif origin is list:
                # Handle list[SomeModel] style annotations (Pydantic collections, etc.).
                args = getattr(expected_type, "__args__", ())
                if args and len(args) == 1:
                    item_type = args[0]
                    if hasattr(item_type, "model_validate") or hasattr(item_type, "parse_obj"):
                        # Convert each incoming item to the declared Pydantic model.
                        validated_list = []
                        for item_value in value:
                            parsed_item = item_value
                            if isinstance(item_value, str):
                                parsed_item = json.loads(item_value)
                            if hasattr(item_type, "model_validate"):
                                validated_list.append(item_type.model_validate(parsed_item))
                            else:  # Fallback for older Pydantic
                                validated_list.append(item_type.parse_obj(parsed_item))
                        validated_args[arg_name] = validated_list
                    else:
                        validated_args[arg_name] = value
                else:
                    validated_args[arg_name] = value
            elif hasattr(expected_type, "model_validate"):
                # Pydantic v2 path – accept raw dicts or JSON strings.
                if isinstance(value, str):
                    value = json.loads(value)
                validated_args[arg_name] = expected_type.model_validate(value)
            elif hasattr(expected_type, "parse_obj"):  # Fallback for older Pydantic
                # Pydantic v1 fallback – same idea as above.
                if isinstance(value, str):
                    value = json.loads(value)
                validated_args[arg_name] = expected_type.parse_obj(value)
            elif expected_type is str:
                validated_args[arg_name] = str(value)
            elif expected_type is int:
                validated_args[arg_name] = int(value)
            elif expected_type is float:
                validated_args[arg_name] = float(value)
            elif expected_type is bool:
                validated_args[arg_name] = bool(value)
            else:
                validated_args[arg_name] = value
        else:
            validated_args[arg_name] = value

    return validated_args


__all__ = ["_normalize_tool_result", "_prepare_tool_arguments"]
