"""Message handler for user prompts."""

import asyncio
import logging
from collections.abc import AsyncGenerator, Sequence
from contextlib import suppress

from ollama import AsyncClient, Image

from agents.ollama.sdk.events import (
    AssistantResponse,
    agent_span,
    event_context,
)
from agents.types import Agent, Data
from config import load_config
from models.model_configs import get_model_by_name

from .computron import computron
from .sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    run_tool_call_loop,
)

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
    """
    if _message_history and _message_history[0].get("role") == "system":
        _message_history.pop(0)
    _message_history.insert(0, {"role": "system", "content": agent.instruction})


async def _handle_image_message(
    message: str,
    data: Sequence[Data],
) -> AsyncGenerator[AssistantResponse, None]:
    """Handles a user message with image data by sending it to the LLM and yielding events.

    Args:
        message (str): The user's message.
        data (Sequence[Data]): Sequence of image data.

    Yields:
        AssistantResponse: Events from the LLM.

    """
    _message_history.extend([{"role": "user", "content": "user added a file:<image/base64>"} for d in data])
    _message_history.append({"role": "user", "content": message})
    log_after_model_call = make_log_after_model_call()
    log_before_model_call = make_log_before_model_call()
    log_before_model_call(_message_history)
    model = get_model_by_name("vision")
    host = config.llm.host if getattr(config, "llm", None) else None
    client = AsyncClient(host=host) if host else AsyncClient()
    response = await client.generate(
        model=model.model,
        prompt=message,
        options=model.options,
        images=[Image(value=d.base64_encoded) for d in data],
        think=model.think,
    )
    content = response.response
    thinking = response.thinking
    _message_history.append(
        {
            "role": "assistant",
            "content": content,
        },
    )
    log_after_model_call(response)
    # Forward as enriched event (non-final). Image flow will receive a final
    # event only once reworked to route through the centralized tool loop path.
    yield AssistantResponse(content=content, thinking=thinking)


async def handle_user_message(
    message: str,
    data: Sequence[Data] | None = None,
) -> AsyncGenerator[AssistantResponse, None]:
    """Handles a user message by sending it to the LLM and yielding events.

    Args:
        message (str): The user's message.
        data (Sequence[Data] | None): Optional sequence of image data.

    Yields:
        AssistantResponse: Events from the LLM.

    """
    if data and len(data) > 0:
        async for event in _handle_image_message(message, data):
            yield event
        return

    try:
        # Bridge published events via a local queue so we can stream results to the caller.
        queue: asyncio.Queue[AssistantResponse | None] = asyncio.Queue()

        async def _queue_handler(evt: AssistantResponse) -> None:
            try:
                await queue.put(evt)
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Failed to enqueue AssistantResponse in message handler")

        async def _producer() -> None:
            agent = computron
            try:
                async with event_context(handler=_queue_handler):
                    with agent_span(agent.name):
                        _message_history.append({"role": "user", "content": message})
                        _insert_system_message(agent)
                        async for _, _ in run_tool_call_loop(
                            messages=_message_history,
                            tools=agent.tools,
                            model=agent.model,
                            think=agent.think,
                            model_options=agent.options,
                            before_model_callbacks=[make_log_before_model_call(agent)],
                            after_model_callbacks=[make_log_after_model_call(agent)],
                        ):
                            pass
            finally:
                await queue.put(None)

        producer_task = asyncio.create_task(_producer())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                # Filter out final events from nested agents (keep everything else)
                if item.final and item.depth is not None and item.depth > 0:
                    continue
                yield item
        finally:
            if not producer_task.done():
                producer_task.cancel()
            with suppress(Exception):
                await producer_task

    except Exception:
        logger.exception("Error handling user message")
        yield AssistantResponse(
            content="An error occurred while processing your message.",
            thinking=None,
            final=True,
        )
