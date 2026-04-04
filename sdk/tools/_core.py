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
    from tools.scratchpad import recall_from_scratchpad, save_to_scratchpad
    from tools.virtual_computer import describe_image, play_audio, send_file

    return [
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
