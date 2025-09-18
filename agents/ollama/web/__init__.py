"""Web research agent package."""

from .agent import (
    after_model_call_callback,
    before_model_call_callback,
    web_agent,
    web_agent_tool,
)

__all__ = [
    "after_model_call_callback",
    "before_model_call_callback",
    "web_agent",
    "web_agent_tool",
]
