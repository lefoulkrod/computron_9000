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

class Data(BaseModel):
    """
    Represents binary or non-text data sent with a user message.

    Attributes:
        base64_encoded (str): The base64-encoded data payload.
        content_type (str): The MIME type of the data (e.g., 'image/png').
    """
    base64_encoded: str
    content_type: str

