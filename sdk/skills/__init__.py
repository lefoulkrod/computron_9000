"""Skill system: progressive tool loading for agents.

Provides AgentState (tracks base tools and loaded skills), the Skill model,
skill registry, and the load_skill / list_available_skills meta-tools.
"""

from ._tools import list_available_skills, load_skill
from ._registry import Skill, get_skill, list_skills, register_skill
from .agent_state import AgentState, get_active_agent_state

__all__ = [
    "AgentState",
    "Skill",
    "get_active_agent_state",
    "get_skill",
    "list_available_skills",
    "list_skills",
    "load_skill",
    "register_skill",
]
