"""The agents package contains AI agent definitions."""

__all__ = [
    "AVAILABLE_AGENTS",
    "AgentProfile",
    "build_llm_options",
    "delete_agent_profile",
    "duplicate_agent_profile",
    "get_agent_profile",
    "get_default_profile",
    "list_agent_profiles",
    "resolve_agent",
    "save_agent_profile",
    "set_model_on_profiles",
]


def __getattr__(name: str) -> object:
    """Lazy imports to avoid circular dependency with sdk."""
    if name in ("AVAILABLE_AGENTS", "resolve_agent"):
        from agents._registry import AVAILABLE_AGENTS, resolve_agent
        return {"AVAILABLE_AGENTS": AVAILABLE_AGENTS, "resolve_agent": resolve_agent}[name]

    _profile_names = (
        "AgentProfile", "build_llm_options", "delete_agent_profile",
        "duplicate_agent_profile", "get_agent_profile", "get_default_profile",
        "list_agent_profiles", "save_agent_profile", "set_model_on_profiles",
    )
    if name in _profile_names:
        from agents._agent_profiles import (
            AgentProfile,
            build_llm_options,
            delete_agent_profile,
            duplicate_agent_profile,
            get_agent_profile,
            get_default_profile,
            list_agent_profiles,
            save_agent_profile,
            set_model_on_profiles,
        )
        return {
            "AgentProfile": AgentProfile,
            "build_llm_options": build_llm_options,
            "delete_agent_profile": delete_agent_profile,
            "duplicate_agent_profile": duplicate_agent_profile,
            "get_agent_profile": get_agent_profile,
            "get_default_profile": get_default_profile,
            "list_agent_profiles": list_agent_profiles,
            "save_agent_profile": save_agent_profile,
            "set_model_on_profiles": set_model_on_profiles,
        }[name]

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
