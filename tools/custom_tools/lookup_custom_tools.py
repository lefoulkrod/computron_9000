"""Tool for discovering and searching saved custom tools."""

from __future__ import annotations

import logging

from . import registry

logger = logging.getLogger(__name__)


def _tool_summary(t: registry.CustomToolDefinition) -> dict[str, object]:
    """Build a summary dict for a tool, always including parameters."""
    summary: dict[str, object] = {
        "name": t.name,
        "description": t.description,
        "type": t.type,
        "language": t.language,
        "tags": t.tags,
    }
    if t.parameters:
        summary["parameters"] = [
            {
                "name": p.name,
                "type": p.type,
                "description": p.description,
                "required": p.required,
            }
            for p in t.parameters
        ]
    return summary


async def lookup_custom_tools(
    action: str = "list",
    query: str = "",
    name: str = "",
) -> dict[str, object]:
    """Look up saved custom tools — list all, search by keyword, or get details of one.

    Args:
        action: "list" to list all tools, "search" to find by keyword,
                "get" for one tool's full details.
        query: One or more search keywords separated by spaces or commas.
            A tool matches if ANY keyword appears in its name, description, or tags.
            Example: "chart, plot, graph" finds tools matching any of those words.
        name: Exact tool name (for get).

    Returns:
        dict with matching tools and their details.
    """
    try:
        if action == "list":
            tools = registry.list_tools()
            return {
                "status": "ok",
                "count": len(tools),
                "tools": [_tool_summary(t) for t in tools],
            }

        if action == "search":
            if not query.strip():
                return {"status": "error", "message": "query is required for search"}
            tools = registry.search_tools(query)
            return {
                "status": "ok",
                "count": len(tools),
                "tools": [_tool_summary(t) for t in tools],
            }

        if action == "get":
            if not name.strip():
                return {"status": "error", "message": "name is required for get"}
            tool = registry.get_tool(name)
            if tool is None:
                return {"status": "not_found", "message": f"No tool named '{name}'"}
            return {"status": "ok", "tool": tool.model_dump()}

        return {"status": "error", "message": f"Unknown action '{action}'. Use 'list', 'search', or 'get'."}

    except Exception as exc:
        logger.exception("Failed to lookup custom tools")
        return {"status": "error", "message": str(exc)}


__all__ = ["lookup_custom_tools"]
