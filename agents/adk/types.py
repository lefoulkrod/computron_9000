"""Common UserMessageEvent model for agent message streaming.

This module has been replaced by agents/types.py. Please use UserMessageEvent from agents/types.py."""

from pydantic import BaseModel

class UserMessageEvent(BaseModel):
    """
    Represents a message event from the agent.

    Attributes:
        message (str): The message content from the agent.
        final (bool): Whether this is the final response in the sequence.
    """
    message: str
    final: bool

