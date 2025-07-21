"""Summary generation utilities for Ollama LLM.

This module provides async functions to generate summaries using Ollama models.
"""

import logging
import re

from ollama import AsyncClient

from config import load_config
from models import get_default_model


class SummaryGenerationError(Exception):
    """Raised when summary generation with Ollama LLM fails."""


logger = logging.getLogger(__name__)
config = load_config()


async def generate_summary_with_ollama(prompt: str, *, think: bool = False) -> str:
    """Generate a summary using the Ollama AsyncClient.

    Args:
        prompt (str): The prompt to send to the LLM.
        think (bool): Whether to enable the 'think' option.

    Returns:
        str: The response from the LLM.

    Raises:
        SummaryGenerationError: If the LLM call fails.

    """
    model = get_default_model()
    try:
        response = await AsyncClient().generate(
            model=model.model,
            prompt=prompt,
            think=think,
            options=model.options,
        )
        logger.debug("Ollama LLM response %s", response.response)
        return re.sub(r"<think>\s*</think>", "", response.response, flags=re.DOTALL)
    except Exception as exc:
        logger.exception("Error in Ollama AsyncClient.generate")
        msg = "Failed to generate summary"
        raise SummaryGenerationError(msg) from exc
