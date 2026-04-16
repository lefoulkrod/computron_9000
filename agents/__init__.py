"""The agents package contains AI agent definitions."""

from agents._agent_builder import build_agent
from agents._agent_profiles import (
    AgentProfile,
    PROFILES_SUBDIR,
    delete_agent_profile,
    duplicate_agent_profile,
    get_agent_profile,
    get_default_profile,
    list_agent_profiles,
    save_agent_profile,
    set_model_on_profiles,
)

__all__ = [
    "AgentProfile",
    "PROFILES_SUBDIR",
    "build_agent",
    "delete_agent_profile",
    "duplicate_agent_profile",
    "get_agent_profile",
    "get_default_profile",
    "list_agent_profiles",
    "save_agent_profile",
    "set_model_on_profiles",
]
