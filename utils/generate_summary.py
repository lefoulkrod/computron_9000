import logging
import re

from config import load_config
from ollama import AsyncClient

logger = logging.getLogger(__name__)
config = load_config()

def _get_ollama_model() -> str:
    """
    Retrieve the Ollama model name from the configuration.

    Returns:
        str: The model name from the config.
    """
    return config.llm.model

async def generate_summary_with_ollama(prompt: str, think: bool = False) -> str:
    """
    Generate a summary using the Ollama AsyncClient.

    Args:
        prompt (str): The prompt to send to the LLM.
        think (bool): Whether to enable the 'think' option.

    Returns:
        str: The response from the LLM.

    Raises:
        RuntimeError: If the LLM call fails.
    """
    model = _get_ollama_model()
    try:
        response = await AsyncClient().generate(
            model=model,
            prompt=prompt,
            think=think
        )
        logger.debug(f"Ollama LLM response: {response.response}")
        cleaned_response = re.sub(r'<think>\s*</think>', '', response.response, flags=re.DOTALL)
        return cleaned_response
    except Exception as e:
        logger.error(f"Error in Ollama AsyncClient.generate: {e}")
        raise RuntimeError(f"Failed to generate summary: {e}") from e
