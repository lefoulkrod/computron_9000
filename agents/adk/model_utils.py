from config import load_config

def get_adk_model() -> str:
    """
    Get the full model string for ADK agents from config.

    Returns:
        str: Provider-prefixed model name.
    """
    config = load_config()
    return f"{config.adk.provider}{config.llm.model}"
