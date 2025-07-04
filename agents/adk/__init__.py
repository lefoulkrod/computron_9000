# This file marks the adk directory as a Python package after moving code.

from .message_handler import handle_user_message
from config import load_config

__all__ = ['handle_user_message']

def get_adk_model() -> str:
    """
    Get the full model string for ADK agents from config.

    Returns:
        str: Provider-prefixed model name.
    """
    config = load_config()
    return f"{config.adk.provider}{config.llm.model}"
