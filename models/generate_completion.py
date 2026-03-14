"""Completion generation utilities.

Provides async function to generate completions using the configured LLM provider.
"""

import logging
from typing import Any

from sdk.providers import get_provider

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
        provider = get_provider()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system or "Generate a response based on the provided prompt."},
            {"role": "user", "content": prompt},
        ]
        response = await provider.chat(
            model=model,
            messages=messages,
            options=options if options is not None else {},
            think=think,
        )
        content = response.message.content or ""
        thinking = response.message.thinking
        logger.debug("Generated response: %s", content)
        logger.debug("Thinking: %s", thinking)
    except Exception as e:
        logger.exception("Error generating completion via provider")
        msg: str = f"Failed to generate completion: {e}"
        raise RuntimeError(msg) from e
    else:
        return content, thinking
