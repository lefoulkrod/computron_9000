import logging
import re

from ollama import AsyncClient

from config import load_config
from models import get_default_model
from models.model_configs import get_model_by_name

logger = logging.getLogger(__name__)
config = load_config()


async def generate_completion(
    prompt: str,
    system: str | None = None,
    think: bool = False,
    model_name: str | None = None,
) -> str:
    """Generate a completion using the Ollama AsyncClient.

    Args:
        prompt (str): The user prompt to send to the LLM.
        system (Optional[str]): The optional system prompt to control the behavior of the LLM.
        think (bool): Whether to enable the 'think' option. Defaults to False.

    Returns:
        str: The response from the LLM.

    Raises:
        RuntimeError: If the LLM call fails.

    """
    if model_name:
        try:
            model = get_model_by_name(model_name)
            logger.debug(f"Using {model.name} model for completion")
        except Exception as e:
            logger.error(f"Model '{model_name}' not found: {e}")
            raise RuntimeError(f"Model '{model_name}' not found") from e
    else:
        # Use the default model if no specific model is provided
        logger.debug("Using default model for completion")
        model = get_default_model()
    try:
        response = await AsyncClient().generate(
            model=model.model,
            prompt=prompt,
            system=system or "Generate a response based on the provided prompt.",
            think=think,
            options=model.options,
        )
        logger.debug(f"Ollama LLM response: {response.response}")

        # Clean any think tags from the response and trim leading/trailing newlines
        cleaned = re.sub(r"<think>([\s\S]*?)</think>", "", response.response, flags=re.DOTALL)
        return cleaned.strip("\n")
    except Exception as e:
        logger.error(f"Error in Ollama AsyncClient.generate: {e}")
        raise RuntimeError(f"Failed to generate completion: {e}") from e
