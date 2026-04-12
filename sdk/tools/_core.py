"""Core tools included in every agent's tool set."""

from collections.abc import Callable
from typing import Any


def get_core_tools() -> list[Callable[..., Any]]:
    """Return tools that every agent gets regardless of skill configuration.

    Lazy imports to avoid circular dependencies.
    """
    from config import load_config
    from sdk.skills._tools import list_available_skills, load_skill
    from sdk.tools._list_profiles import list_agent_profiles
    from sdk.tools._spawn_agent import spawn_agent
    from tools.scratchpad import recall_from_scratchpad, save_to_scratchpad
    from tools.virtual_computer.describe_image import describe_image
    from tools.virtual_computer.file_output import send_file
    from tools.virtual_computer.play_audio import play_audio

    tools = [
        save_to_scratchpad,
        recall_from_scratchpad,
        load_skill,
        list_available_skills,
        list_agent_profiles,
        spawn_agent,
        send_file,
        play_audio,
        describe_image,
    ]
    if load_config().features.custom_tools:
        from tools.custom_tools import create_custom_tool, lookup_custom_tools, run_custom_tool
        tools.extend([create_custom_tool, lookup_custom_tools, run_custom_tool])
    return tools
