"""Message handler for user prompts."""

import logging
from collections.abc import AsyncGenerator, Sequence

from ollama import AsyncClient, Image

from agents.types import Agent, Data, UserMessageEvent
from config import load_config
from models.model_configs import get_default_model

from .computron_agent import computron
from .deep_researchV2 import coordinator
from .root_agent import handoff_agent_tool
from .sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    run_tool_call_loop,
    split_think_content,
)
from .web_agent import web_agent

logger = logging.getLogger(__name__)

config = load_config()

# Module-level message history for chat session, initialized with system message
_message_history: list[dict[str, str]] = []


def reset_message_history() -> None:
    """Resets the message history to the initial system message."""
    _message_history.clear()


def _insert_system_message(agent: Agent) -> None:
    """Removes the first system message and inserts a new system message at the beginningof the message history.

    Args:
        agent (Agent): The agent whose instruction will be set as the new system message.
    """  # noqa: E501
    if _message_history and _message_history[0].get("role") == "system":
        _message_history.pop(0)
    _message_history.insert(0, {"role": "system", "content": agent.instruction})


async def _handle_image_message(
    message: str,
    data: Sequence[Data],
) -> AsyncGenerator[UserMessageEvent, None]:
    """Handles a user message with image data by sending it to the LLM and yielding events.

    Args:
        message (str): The user's message.
        data (Sequence[Data]): Sequence of image data.

    Yields:
        UserMessageEvent: Events from the LLM.

    """
    log_after_model_call = make_log_after_model_call()
    log_before_model_call = make_log_before_model_call()
    _message_history.extend(
        [{"role": "user", "content": f"<image/base64>{d.base64_encoded}"} for d in data]
    )
    _message_history.append({"role": "user", "content": message})
    log_before_model_call(_message_history)
    model = get_default_model()
    response = await AsyncClient().generate(
        model=model.model,
        prompt=message,
        options=model.options,
        images=[Image(value=d.base64_encoded) for d in data],
    )
    main_text, thinking = split_think_content(response.response)
    _message_history.append(
        {
            "role": "assistant",
            "content": main_text,
        },
    )
    log_after_model_call(response)
    yield UserMessageEvent(message=main_text, final=True, thinking=thinking)


async def handle_user_message(
    message: str,
    data: Sequence[Data] | None = None,
) -> AsyncGenerator[UserMessageEvent, None]:
    """Handles a user message by sending it to the LLM and yielding events.

    Args:
        message (str): The user's message.
        data (Sequence[Data] | None): Optional sequence of image data.

    Yields:
        UserMessageEvent: Events from the LLM.

    """
    try:
        # Use the handoff agent to process the message and run the appropriate agent
        agent_to_run = await handoff_agent_tool(message)
        logger.debug("Using agent: %s", agent_to_run)
        if agent_to_run == "computron":
            agent = computron
        elif agent_to_run == "web":
            agent = web_agent
        elif agent_to_run == "research":
            agent = coordinator
        else:
            agent = computron
        _insert_system_message(agent)
        log_before_model_call = make_log_before_model_call(agent)
        log_after_model_call = make_log_after_model_call(agent)

        if data and len(data) > 0:
            async for event in _handle_image_message(message, data):
                yield event
            return

        _message_history.append({"role": "user", "content": message})

        async for content in run_tool_call_loop(
            messages=_message_history,
            tools=agent.tools,
            model=agent.model,
            model_options=agent.options,
            before_model_callbacks=[log_before_model_call],
            after_model_callbacks=[log_after_model_call],
        ):
            if content is not None:
                main_text, thinking = split_think_content(content)
                yield UserMessageEvent(
                    message=main_text,
                    final=False,
                    thinking=thinking,
                )
    except Exception:
        logger.exception("Error handling user message")
        yield UserMessageEvent(
            message="An error occurred while processing your message.",
            final=True,
            thinking=None,
        )
