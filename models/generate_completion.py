"""Completion generation utilities for Ollama LLM.

Provides async function to generate completions using Ollama AsyncClient.
"""

import logging
from typing import Any

from ollama import AsyncClient

from config import load_config

logger = logging.getLogger(__name__)


async def generate_completion(
    prompt: str,
    model: str,
    *,
    system: str | None = None,
    think: bool = False,
    options: dict[str, Any] | None = None,
) -> tuple[str, str | None]:
    """Generate a completion using the model.

    Args:
        prompt (str): The user prompt to send to the LLM.
        model (str): The model name to use for completion.
        system (Optional[str]): The optional system prompt to control the behavior of the LLM.
        think (bool): Whether to enable the 'think' option. Defaults to False.
        options (Optional[dict[str, Any]]): Additional options for the model.

    Returns:
        tuple[str, str | None]: Tuple of the response and any thinking in that order.

    Raises:
        RuntimeError: If the LLM call fails.
    """
    try:
        cfg = load_config()
        if getattr(cfg, "llm", None) and cfg.llm.host:
            client = AsyncClient(host=cfg.llm.host)
        else:
            client = AsyncClient()
        response = await client.generate(
            model=model,
            prompt=prompt,  # prompt_to_send,
            system=system or "Generate a response based on the provided prompt.",
            options=options if options is not None else {},
            think=think,
        )
        logger.debug("Generated response: %s", response.response)
        logger.debug("Thinking: %s", response.thinking)
    except Exception as e:
        logger.exception("Error in Ollama AsyncClient.generate")
        msg: str = f"Failed to generate completion: {e}"
        raise RuntimeError(msg) from e
    else:
        return response.response, response.thinking
