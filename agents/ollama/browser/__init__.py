"""Browser agent package.

Public API:
- browser_agent: Configured agent instance for simple web page summarization.
- browser_agent_tool: Callable wrapper to run the agent as a tool.
"""

from .agent import browser_agent, browser_agent_tool

__all__ = [
    "browser_agent",
    "browser_agent_tool",
]
