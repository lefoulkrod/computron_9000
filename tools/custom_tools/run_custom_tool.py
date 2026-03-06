"""Tool for executing saved custom tools inside the container."""

from __future__ import annotations

import json
import logging

from . import registry
from .executor import execute_custom_tool

logger = logging.getLogger(__name__)


async def run_custom_tool(
    name: str,
    arguments_json: str = "{}",
) -> dict[str, object]:
    """Execute a saved custom tool inside the container environment.

    Runs the tool by name with the provided arguments. Command-type tools
    interpolate arguments into the shell template. Program-type tools receive
    arguments as JSON on stdin.

    Args:
        name: The name of the custom tool to run.
        arguments_json: JSON object of arguments matching the tool's parameter definitions.

    Returns:
        dict with stdout, stderr, and exit_code from the execution.
    """
    try:
        tool_def = registry.get_tool(name)
        if tool_def is None:
            # Auto-search for similar tools so the agent doesn't need a separate lookup call
            suggestions = registry.search_tools(name)
            if suggestions:
                names = ", ".join(t.name for t in suggestions)
                return {
                    "status": "not_found",
                    "message": f"No custom tool named '{name}'. Similar tools: {names}",
                    "suggestions": [
                        {"name": t.name, "description": t.description}
                        for t in suggestions
                    ],
                }
            return {
                "status": "not_found",
                "message": f"No custom tool named '{name}' and no similar tools found.",
            }

        try:
            arguments = json.loads(arguments_json)
        except json.JSONDecodeError as exc:
            return {"status": "error", "message": f"Invalid arguments_json: {exc}"}

        if not isinstance(arguments, dict):
            return {"status": "error", "message": "arguments_json must be a JSON object"}

        # Validate required parameters
        for param in tool_def.parameters:
            if param.required and param.name not in arguments:
                return {"status": "error", "message": f"Missing required parameter '{param.name}'"}

        result = await execute_custom_tool(tool_def, arguments)

        # Return a compact result to minimize context usage.
        # Only include stderr when there's no stdout (likely an error).
        stdout = str(result.get("stdout") or "").strip()
        stderr = str(result.get("stderr") or "").strip()
        exit_code = result.get("exit_code")
        if exit_code == 0 or exit_code is None:
            return {"stdout": stdout} if stdout else result
        # Non-zero exit: include stderr only when stdout is empty
        if stdout:
            return {"stdout": stdout, "exit_code": exit_code}
        return {"stderr": stderr or "Command failed", "exit_code": exit_code}

    except Exception as exc:
        logger.exception("Failed to run custom tool '%s'", name)
        return {"status": "error", "message": str(exc)}


__all__ = ["run_custom_tool"]
