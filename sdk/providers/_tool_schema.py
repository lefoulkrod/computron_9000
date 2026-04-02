"""Utility for converting Python callables to JSON schema tool definitions.

Needed by OpenAI and Anthropic providers which require explicit JSON schema
for tool definitions (unlike Ollama which accepts raw callables).
"""

import inspect
import logging
import re
import types
from collections.abc import Callable
from typing import Any, Union, get_args, get_origin

logger = logging.getLogger(__name__)

# Mapping of Python types to JSON Schema types.
_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}

# Matches a Google-style arg line: leading whitespace, param name, colon,
# then optional type in parens, then the description.
_ARG_LINE_RE = re.compile(
    r"^\s{4,}(\w+)"          # indented param name
    r"(?:\s*\([^)]*\))?"     # optional (type) — we already know the type
    r"\s*:\s*"               # colon separator
    r"(.+)",                 # description text
)


def _parse_arg_descriptions(docstring: str | None) -> dict[str, str]:
    """Extract per-parameter descriptions from a Google-style docstring.

    Args:
        docstring: The raw docstring text (may be None).

    Returns:
        Mapping of parameter name to its description string.
    """
    if not docstring:
        return {}

    descriptions: dict[str, str] = {}
    lines = docstring.split("\n")
    in_args = False
    current_param: str | None = None
    current_desc_parts: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Detect start of Args section
        if stripped in ("Args:", "Arguments:"):
            in_args = True
            continue

        # Detect end of Args section (another section header or blank after content)
        if in_args and stripped and stripped.endswith(":") and not stripped.startswith(" "):
            # Save any in-progress param
            if current_param is not None:
                descriptions[current_param] = " ".join(current_desc_parts).strip()
            break

        if not in_args:
            continue

        # Try matching a new arg line
        m = _ARG_LINE_RE.match(line)
        if m:
            # Save previous param
            if current_param is not None:
                descriptions[current_param] = " ".join(current_desc_parts).strip()
            current_param = m.group(1)
            current_desc_parts = [m.group(2).strip()]
        elif current_param is not None and stripped:
            # Continuation line for current param
            current_desc_parts.append(stripped)

    # Save last param
    if current_param is not None:
        descriptions[current_param] = " ".join(current_desc_parts).strip()

    return descriptions


def _python_type_to_json_schema(annotation: Any) -> dict[str, Any]:
    """Convert a Python type annotation to a JSON Schema type descriptor."""
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {"type": "string"}

    origin = get_origin(annotation)
    if origin is list:
        args = get_args(annotation)
        items = _python_type_to_json_schema(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": items}

    if origin is dict:
        return {"type": "object"}

    # Handle Optional (Union[X, None])
    if origin is Union or origin is types.UnionType:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return _python_type_to_json_schema(args[0])

    json_type = _TYPE_MAP.get(annotation, "string")
    return {"type": json_type}


# Section header prefixes that end the description body (case-insensitive).
_SECTION_PREFIXES = ("args:", "arguments:", "returns:", "raises:", "yields:", "note:", "notes:", "examples:", "example:")


def _extract_description(docstring: str | None) -> str:
    """Extract the full description text from a Google-style docstring.

    Returns everything before the first section header (Args, Returns, etc.),
    collapsed into a single paragraph.
    """
    if not docstring:
        return ""
    lines: list[str] = []
    for line in docstring.strip().splitlines():
        if line.strip().lower().startswith(_SECTION_PREFIXES):
            break
        lines.append(line.strip())
    # Collapse into a single string, dropping empty lines at boundaries.
    return " ".join(part for part in lines if part)


def callable_to_json_schema(func: Callable[..., Any]) -> dict[str, Any]:
    """Convert a Python callable into an OpenAI-style tool JSON schema.

    Args:
        func: The callable to convert.

    Returns:
        A dict matching the OpenAI tool schema format.
    """
    sig = inspect.signature(func)
    docstring = inspect.getdoc(func)
    arg_descs = _parse_arg_descriptions(docstring)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        prop = _python_type_to_json_schema(param.annotation)
        desc = arg_descs.get(name)
        if desc:
            prop["description"] = desc
        properties[name] = prop
        if param.default is inspect.Parameter.empty:
            required.append(name)

    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": _extract_description(docstring),
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }
