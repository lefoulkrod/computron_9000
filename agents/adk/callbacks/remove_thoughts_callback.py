import logging
from typing import Any

from google.adk.models.llm_request import LlmRequest
from google.adk.agents.callback_context import CallbackContext
from google.genai.types import Content, Part

logger = logging.getLogger(__name__)

def remove_thoughts_callback(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> None:
    """
    Callback to remove any content parts that start with the text '<think>' from the LLM request.

    Args:
        callback_context (CallbackContext): The callback context for the agent.
        llm_request (LlmRequest): The request sent to the LLM model. Mutated in place.

    Returns:
        None
    """
    try:
        for content in llm_request.contents:
            if not hasattr(content, 'parts') or not content.parts:
                continue
            # Only keep parts that do not start with '<think>'
            filtered_parts = []
            for part in content.parts:
                text = getattr(part, 'text', None)
                if text is not None and isinstance(text, str) and text.startswith("<think>"):
                    logger.debug(f"Agent [{callback_context.agent_name}] Removed part starting with <think>: {text}")
                    continue
                filtered_parts.append(part)
            content.parts = filtered_parts
    except Exception as exc:
        logger.error(f"Agent [{callback_context.agent_name}] Error in remove_thoughts_callback: {exc}", exc_info=True)
        raise
