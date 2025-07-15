import logging
import re

from ollama import AsyncClient

from config import load_config
from models import get_default_model

logger = logging.getLogger(__name__)
config = load_config()


async def generate_summary_with_ollama(prompt: str, think: bool = False) -> str:
    """Generate a summary using the Ollama AsyncClient.

    Args:
        prompt (str): The prompt to send to the LLM.
        think (bool): Whether to enable the 'think' option.

    Returns:
        str: The response from the LLM.

    Raises:
        RuntimeError: If the LLM call fails.

    """
    model = get_default_model()
    try:
        response = await AsyncClient().generate(
            model=model.model,
            prompt=prompt,
            think=think,
        )
        logger.debug(f"Ollama LLM response: {response.response}")
        return re.sub(r"<think>\s*</think>", "", response.response, flags=re.DOTALL)
    except Exception as e:
        logger.error(f"Error in Ollama AsyncClient.generate: {e}")
        raise RuntimeError(f"Failed to generate summary: {e}") from e
