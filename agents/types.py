"""Common UserMessageEvent model for agent message streaming, shared across agents package."""

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

