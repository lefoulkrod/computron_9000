"""Tool adapter for MCP tools - converts MCP tools to COMPUTRON_9000 format."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, create_model

from sdk.tools._schema import JSONValue

from tools.mcp.registry import get_mcp_registry

logger = logging.getLogger(__name__)


def _mcp_type_to_python(mcp_type: str) -> type:
    """Convert MCP type to Python type."""
    type_map = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    return type_map.get(mcp_type, Any)


def _create_pydantic_model_from_schema(
    name: str,
    schema: dict[str, Any]
) -> type[BaseModel]:
    """Create a Pydantic model from JSON schema."""
    fields = {}
    required = schema.get("required", [])
    properties = schema.get("properties", {})

    for prop_name, prop_schema in properties.items():
        prop_type = _mcp_type_to_python(prop_schema.get("type", "string"))
        description = prop_schema.get("description", "")

        if prop_name in required:
            fields[prop_name] = (prop_type, ...)
        else:
            fields[prop_name] = (prop_type | None, None)

    return create_model(name, **fields)


def convert_mcp_tools(
    mcp_tools: list[dict[str, Any]]
) -> list[Callable[..., Any]]:
    """Convert MCP tool definitions to COMPUTRON_9000 callable tools."""
    tools = []

    for tool_def in mcp_tools:
        tool_name = tool_def["name"]
        tool_description = tool_def.get("description", "")
        parameters_schema = tool_def.get("parameters", {})

        # Create Pydantic model for parameters
        ParamModel = _create_pydantic_model_from_schema(
            f"{tool_name}Params",
            parameters_schema
        )

        # Create the tool function
        def create_tool_function(name: str, description: str, model: type[BaseModel]) -> Callable[..., Any]:
            async def mcp_tool(**kwargs: Any) -> JSONValue:
                """MCP tool wrapper."""
                registry = get_mcp_registry()
                client = registry.get_client_for_tool(name)

                if not client:
                    return {"error": f"MCP client for tool '{name}' not found"}

                # Strip prefix for actual MCP call
                original_name = registry.strip_prefix(name)

                try:
                    result = await client.call_tool(original_name, kwargs)
                    return _normalize_mcp_result(result)
                except Exception as e:
                    logger.exception("MCP tool '%s' failed", name)
                    return {"error": str(e)}

            # Set function metadata for tool schema generation
            mcp_tool.__name__ = name
            mcp_tool.__doc__ = description
            mcp_tool.__annotations__ = {**model.__annotations__, "return": JSONValue}

            return mcp_tool

        tool_func = create_tool_function(tool_name, tool_description, ParamModel)
        tools.append(tool_func)

    return tools


def _normalize_mcp_result(result: Any) -> JSONValue:
    """Normalize MCP tool result for COMPUTRON_9000."""
    if isinstance(result, BaseModel):
        return result.model_dump()
    elif isinstance(result, list):
        return [_normalize_mcp_result(item) for item in result]
    elif isinstance(result, dict):
        return {k: _normalize_mcp_result(v) for k, v in result.items()}
    return result


async def execute_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    """Execute an MCP tool by name with given arguments."""
    registry = get_mcp_registry()
    client = registry.get_client_for_tool(tool_name)

    if not client:
        raise ValueError(f"MCP tool '{tool_name}' not available")

    original_name = registry.strip_prefix(tool_name)
    return await client.call_tool(original_name, arguments)
