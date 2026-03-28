"""Tool utilities: argument preparation, result normalization, schemas, and agent wrappers.

The agent wrapper (``_agent_wrapper``) has heavy cross-SDK dependencies and is
imported lazily to avoid circular imports.  Access ``make_run_agent_as_tool_function``
and related names via ``sdk.tools._agent_wrapper`` or the top-level ``sdk`` package.
"""

from ._helpers import _execute_tool_call, _normalize_tool_result, _prepare_tool_arguments
from ._schema import JSONValue, model_placeholder_shape, model_to_schema
from ._truncation import truncate_args, truncate_tool_call_args

__all__ = [
    "JSONValue",
    "_execute_tool_call",
    "_normalize_tool_result",
    "_prepare_tool_arguments",
    "model_placeholder_shape",
    "model_to_schema",
    "truncate_args",
    "truncate_tool_call_args",
]


def __getattr__(name: str) -> object:
    """Lazy imports for names with heavy cross-SDK dependencies."""
    _lazy = {
        "AgentToolConversionError",
        "AgentToolMarker",
        "make_run_agent_as_tool_function",
    }
    if name in _lazy:
        from . import _agent_wrapper

        return getattr(_agent_wrapper, name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
