"""Completion generation utilities for Ollama LLM.

Provides async function to generate completions using Ollama AsyncClient.
"""

import logging
import re
from typing import Any

from ollama import AsyncClient

logger = logging.getLogger(__name__)


async def generate_completion(
    prompt: str,
    model: str,
    *,
    system: str | None = None,
    think: bool = False,
    options: dict[str, Any] | None = None,
) -> str:
    """Generate a completion using the model.

    Args:
        prompt (str): The user prompt to send to the LLM.
        model (str): The model name to use for completion.
        system (Optional[str]): The optional system prompt to control the behavior of the LLM.
        think (bool): Whether to enable the 'think' option. Defaults to False.
        options (Optional[dict[str, Any]]): Additional options for the model.

    Returns:
        str: The response from the LLM.

    Raises:
        RuntimeError: If the LLM call fails.
    """
    try:
        response = await AsyncClient().generate(
            model=model,
            prompt=prompt,
            system=system or "Generate a response based on the provided prompt.",
            options=options if options is not None else {},
            think=think,
        )
        logger.debug("Generated response: %s", response.response)

        # Clean any think tags from the response and trim leading/trailing newlines
        cleaned = re.sub(r"<think>([\s\S]*?)</think>", "", response.response, flags=re.DOTALL)
        return cleaned.strip("\n")
    except Exception as e:
        logger.exception("Error in Ollama AsyncClient.generate")
        msg: str = f"Failed to generate completion: {e}"
        raise RuntimeError(msg) from e
