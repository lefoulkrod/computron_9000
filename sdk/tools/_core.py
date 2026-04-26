"""Core tools included in every agent's tool set."""

from collections.abc import Callable
from typing import Any


async def get_core_tools() -> list[Callable[..., Any]]:
    """Return tools that every agent gets regardless of skill configuration.

    Async because the integration tool gating awaits the integrations cache,
    which loads lazily on first use after app startup.

    Lazy imports to avoid circular dependencies.
    """
    from config import load_config
    from sdk.skills._tools import list_available_skills, load_skill
    from agents._list_profiles_tool import list_agent_profiles
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

    # Integration-bound tools are gated by capability — the supervisor's
    # catalog declares which capabilities each provider offers, surfaced in
    # the list/add RPC responses. The tool's dynamic docstring lists the
    # currently-registered IDs so the model picks a real one instead of
    # guessing.
    from tools.integrations import registered_integrations
    records = await registered_integrations()
    # Only running integrations get their tools surfaced — auth_failed /
    # broken integrations would just produce errors when the agent calls
    # them, so hide them until the user re-adds.
    email_ids = frozenset(
        i for i, rec in records.items()
        if "email" in rec.capabilities and rec.state == "running"
    )
    if email_ids:
        from tools.integrations.list_email_folders import build_list_email_folders_tool
        from tools.integrations.list_email_messages import build_list_email_messages_tool
        from tools.integrations.read_email_message import build_read_email_message_tool
        from tools.integrations.search_email import build_search_email_tool
        tools.append(build_list_email_folders_tool(email_ids))
        tools.append(build_list_email_messages_tool(email_ids))
        tools.append(build_read_email_message_tool(email_ids))
        tools.append(build_search_email_tool(email_ids))

    calendar_ids = frozenset(
        i for i, rec in records.items()
        if "calendar" in rec.capabilities and rec.state == "running"
    )
    if calendar_ids:
        from tools.integrations.list_calendars import build_list_calendars_tool
        from tools.integrations.list_events import build_list_events_tool
        tools.append(build_list_calendars_tool(calendar_ids))
        tools.append(build_list_events_tool(calendar_ids))

    return tools
