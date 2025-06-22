"""
callbacks.py

Shared callback functions for the ADK agents.
"""

import logging

from google.adk.models.llm_response import LlmResponse
from google.adk.models.llm_request import LlmRequest
from google.adk.agents.callback_context import CallbackContext
from google.genai.types import Content, Part

logger = logging.getLogger(__name__)

def _collect_content_parts_log_lines(contents: list[Content], agent_name: str, banner_color: str, direction: str) -> list[str]:
    """
    Collects log lines for content parts for LLM requests or responses.

    Args:
        contents (list[Content]): List of Content objects.
        agent_name (str): Name of the agent for logging context.
        banner_color (str): ANSI color code for the banner.
        direction (str): 'Request To' or 'Response From' for banner labeling.

    Returns:
        list[str]: List of formatted log lines for the content parts.
    """
    lines = [
        f"\n{banner_color}Agent [{agent_name}] {direction} LLM {'='*30}"
    ]
    for content_idx, content in enumerate(contents):
        parts = content.parts
        if not parts:
            continue
        for idx, part in enumerate(parts):
            part_lines = [f"Content {content_idx+1} Part {idx+1}:"]
            if hasattr(part, 'text') and part.text:
                part_lines.append(f"  [text]: {part.text}")
            if hasattr(part, 'function_call') and part.function_call:
                part_lines.append(f"  [function_call]: {part.function_call}")
            if hasattr(part, 'function_response') and part.function_response:
                part_lines.append(f"  [function_response]: {part.function_response}")
            if hasattr(part, 'thought') and part.thought is not None:
                part_lines.append(f"  [thought]: {part.thought}")
            if len(part_lines) > 1:
                lines.extend(part_lines)
    lines.append(f"{'='*45}\033[0m")
    return lines


def log_llm_response_callback(
    callback_context: CallbackContext, llm_response: LlmResponse
) -> None:
    """
    Callback function for LlmAgent. Logs the LLM response and, if present, logs the text part in a more readable way.

    Args:
        callback_context (CallbackContext): The callback context for the agent.
        llm_response (LlmResponse): The response from the LLM model.

    Returns:
        None
    """
    try:
        content = llm_response.content
        if content:
            lines = _collect_content_parts_log_lines([content], callback_context.agent_name, "\033[93m", "Response From")
            logger.debug("\n" + "\n".join(lines))
    except Exception as exc:
        logger.error(f"Error in log_llm_response_callback: {exc}", exc_info=True)
    return None


def log_llm_request_callback(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> None:
    """
    Callback function for LlmAgent. Logs the LLM request in a structured, readable format with a green banner.

    Args:
        callback_context (CallbackContext): The callback context for the agent.
        llm_request (LlmRequest): The request sent to the LLM model.

    Returns:
        None
    """
    try:
        contents = llm_request.contents
        if not llm_request.contents or all((c.parts is None or len(c.parts) == 0) for c in contents):
            logger.debug(f"Agent [{callback_context.agent_name}] Request To LLM: No Content Parts")
            return
        lines = _collect_content_parts_log_lines(contents, callback_context.agent_name, "\033[92m", "Request To")
        logger.debug("\n" + "\n".join(lines))
    except Exception as exc:
        logger.error(f"Error in log_llm_request_callback: {exc}", exc_info=True)
    return None

