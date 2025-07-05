import logging
import pprint
from typing import Callable, Any

from ollama import ChatResponse

logger = logging.getLogger(__name__)

def make_log_before_model_call(agent: Any) -> Callable[[list[dict[str, str]]], None]:
    """
    Factory for a callback that logs the chat history before calling the model.

    Args:
        agent (Any): The agent object with a 'name' attribute.

    Returns:
        Callable[[list[dict[str, str]]], None]: The logging callback.
    """
    def log_before_model_call(messages: list[dict[str, str]]) -> None:
        agent_name = getattr(agent, 'name', 'unknown')
        log_text = (
            f"\n========== [before_model_call] for agent: {agent_name} =========="
            f"\nChat history sent to LLM:\n{pprint.pformat(messages)}"
        )
        logger.debug("\033[32m%s\033[0m", log_text)
    return log_before_model_call

def make_log_after_model_call(agent: Any) -> Callable[[ChatResponse], None]:
    """
    Factory for a callback that logs the LLM response and stats after the model call.

    Args:
        agent (Any): The agent object with a 'name' attribute.

    Returns:
        Callable[[ChatResponse], None]: The logging callback.
    """
    def log_after_model_call(response: ChatResponse) -> None:
        agent_name = getattr(agent, 'name', 'unknown')
        log_text = f"\n========== [after_model_call] for agent: {agent_name} =========="
        # Log LLM stats if present
        if hasattr(response, 'done') and getattr(response, 'done', False):
            from agents.ollama.sdk import llm_runtime_stats
            stats = llm_runtime_stats(response)
            log_text += (
                f"\nLLM stats:\n"
                f"  total_duration:         {getattr(stats, 'total_duration', 0) or 0:.3f}s\n"
                f"  load_duration:          {getattr(stats, 'load_duration', 0) or 0:.3f}s\n"
                f"  prompt_eval_count:      {getattr(stats, 'prompt_eval_count', 0)}\n"
                f"  prompt_eval_duration:   {getattr(stats, 'prompt_eval_duration', 0) or 0:.3f}s\n"
                f"  prompt_tokens_per_sec:  {getattr(stats, 'prompt_tokens_per_sec', 0) or 0:.2f}\n"
                f"  eval_count:             {getattr(stats, 'eval_count', 0)}\n"
                f"  eval_duration:          {getattr(stats, 'eval_duration', 0) or 0:.3f}s\n"
                f"  eval_tokens_per_sec:    {getattr(stats, 'eval_tokens_per_sec', 0) or 0:.2f}\n"
            )
        try:
            response_data = response.model_dump()
            log_text += f"\nLLM response:\n{pprint.pformat(response_data)}"
        except Exception:
            log_text += "\nLLM response: <model_dump failed>"
        logger.debug("\033[33m%s\033[0m", log_text)
    return log_after_model_call
