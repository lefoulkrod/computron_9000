"""Ollama agent package exposing all public agents and message handler."""
from .web_agent import web_agent
from .computron_agent import computron
from .root_agent import root_agent
from .message_handler import handle_user_message

__all__ = [
    "web_agent",
    "computron",
    "root_agent",
    "handle_user_message",
]
