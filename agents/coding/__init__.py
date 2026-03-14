"""General-purpose computer agent package.

Public API:
- computer_agent_tool: Callable wrapper to run the agent as a tool.
- NAME, DESCRIPTION, SYSTEM_PROMPT, TOOLS: Static agent config constants.
"""

from .agent import (
    DESCRIPTION,
    NAME,
    SYSTEM_PROMPT,
    TOOLS,
    computer_agent_tool,
)

__all__ = [
    "DESCRIPTION",
    "NAME",
    "SYSTEM_PROMPT",
    "TOOLS",
    "computer_agent_tool",
]
