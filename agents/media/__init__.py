"""GPU inference agent package.

Public API:
- inference_agent_tool: Callable wrapper to run the agent as a tool.
- media_agent_tool: Backward-compatible alias for inference_agent_tool.
- NAME, DESCRIPTION, SYSTEM_PROMPT, TOOLS: Static agent config constants.
"""

from .agent import (
    DESCRIPTION,
    NAME,
    SYSTEM_PROMPT,
    TOOLS,
    inference_agent_tool,
    media_agent_tool,
)

__all__ = [
    "DESCRIPTION",
    "NAME",
    "SYSTEM_PROMPT",
    "TOOLS",
    "inference_agent_tool",
    "media_agent_tool",
]
