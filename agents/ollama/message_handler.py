import logging
import pprint
from typing import AsyncGenerator, Sequence

from ollama import ChatResponse

from agents.types import UserMessageEvent, Data
from config import load_config
from .computron_agent import computron
from .sdk import run_tool_call_loop, split_think_content, make_log_before_model_call, make_log_after_model_call

logger = logging.getLogger(__name__)

config = load_config()

agent = computron

# Module-level message history for chat session, initialized with system message
_message_history: list[dict[str, str]] = [
    {'role': 'system', 'content': agent.instruction}
]

log_before_model_call = make_log_before_model_call(agent)
log_after_model_call = make_log_after_model_call(agent)

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
            before_model_callbacks=[log_before_model_call],
            after_model_callbacks=[log_after_model_call]
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