"""Core tools included in every agent's tool set."""

from collections.abc import Callable
from typing import Any


def get_core_tools() -> list[Callable[..., Any]]:
    """Return tools that every agent gets regardless of skill configuration.

    Lazy imports to avoid circular dependencies.
    """
    from sdk.skills._tools import list_available_skills, load_skill
    from sdk.tools._spawn_agent import spawn_agent
    from tools.custom_tools import create_custom_tool, lookup_custom_tools, run_custom_tool
    from tools.mcp import convert_mcp_tools, get_mcp_registry
    from tools.scratchpad import recall_from_scratchpad, save_to_scratchpad
    from tools.virtual_computer import describe_image, play_audio, send_file

    core_tools = [
        save_to_scratchpad,
        recall_from_scratchpad,
        load_skill,
        list_available_skills,
        spawn_agent,
        create_custom_tool,
        lookup_custom_tools,
        run_custom_tool,
        send_file,
        play_audio,
        describe_image,
    ]

    # Add MCP tools if MCP is enabled
    registry = get_mcp_registry()
    if registry.config.enabled:
        mcp_tools = registry.get_all_tools()
        if mcp_tools:
            converted = convert_mcp_tools(mcp_tools)
            core_tools.extend(converted)

    return core_tools
