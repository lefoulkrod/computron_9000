# This file marks the adk directory as a Python package after moving code.

from config import load_config
from .callbacks import (
    log_llm_request_callback,
    log_llm_response_callback,
    remove_thoughts_callback,
)

def get_adk_model() -> str:
    """
    Get the full model string for ADK agents from config.

    Returns:
        str: Provider-prefixed model name.
    """
    config = load_config()
    return f"{config.adk.provider}{config.llm.model}"
