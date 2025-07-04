import logging
import pprint
from typing import AsyncGenerator, Sequence

from ollama import ChatResponse

from agents.types import UserMessageEvent, Data
from config import load_config
from .agents import computron, root_agent
from agents.ollama.sdk import run_tool_call_loop, split_think_content

logger = logging.getLogger(__name__)

config = load_config()

agent = computron

# Module-level message history for chat session, initialized with system message
_message_history: list[dict[str, str]] = [
    {'role': 'system', 'content': agent.instruction}
]

def _log_before_model_call(messages: list[dict[str, str]]) -> None:
    """
    Logs the chat history before calling the model.

    Args:
        messages (list[dict[str, str]]): The chat history.
    """
    agent_name = getattr(agent, 'name', 'unknown')
    log_text = (
        f"\n========== [before_model_call] for agent: {agent_name} =========="
        f"\nChat history sent to LLM:\n{pprint.pformat(messages)}"
    )
    logger.debug("\033[32m%s\033[0m", log_text)

def _log_after_model_call(response: ChatResponse) -> None:
    """
    Logs the LLM response and stats after the model call.

    Args:
        response (ChatResponse): The LLM response object.
    """
    agent_name = getattr(agent, 'name', 'unknown')
    log_text = f"\n========== [after_model_call] for agent: {agent_name} =========="
    # Log LLM stats if present
    if hasattr(response, 'done') and getattr(response, 'done', False):
        from agents.ollama.sdk.tool_loop import _llm_runtime_stats
        stats = _llm_runtime_stats(response)
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
    # Use model_dump for pretty printing if available (Pydantic BaseModel)
    model_dump = getattr(response, 'model_dump', None)
    if callable(model_dump):
        try:
            response_data = model_dump()
            log_text += f"\nLLM response:\n{pprint.pformat(response_data)}"
        except Exception:
            log_text += "\nLLM response: <model_dump failed>"
    logger.debug("\033[33m%s\033[0m", log_text)

async def handle_user_message(
    message: str,
    data: Sequence[Data] | None = None, 
    stream: bool = False
) -> AsyncGenerator[UserMessageEvent, None]:
    """
    Handles a user message by sending it to the LLM and yielding events.

    Args:
        message (str): The user's message.
        stream (bool): Whether to stream responses.

    Yields:
        UserMessageEvent: Events from the LLM.
    """
    # Append the new user message to the session history
    _message_history.append({'role': 'user', 'content': message})
    try:
        async for content in run_tool_call_loop(
            messages=_message_history,
            tools=agent.tools,
            model=agent.model,
            model_options=agent.options,
            before_model_call=_log_before_model_call,
            after_model_call=_log_after_model_call
        ):
            if content is not None:
                main_text, thinking = split_think_content(content)
                yield UserMessageEvent(
                    message=main_text,
                    final=False,
                    thinking=thinking
                )
    except Exception as exc:
        logger.exception(f"Error handling user message: {exc}")
        yield UserMessageEvent(message="An error occurred while processing your message.", final=True, thinking=None)