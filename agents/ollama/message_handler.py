"""Message handler for user prompts."""

import asyncio
import logging
from collections.abc import AsyncGenerator, Sequence

from ollama import AsyncClient, Image

from agents.ollama.sdk.events import AssistantResponse, DispatchEvent, event_context
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
    """  # noqa: E501
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
    _message_history.extend(
        [{"role": "user", "content": "user added a file:<image/base64>"} for d in data]
    )
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
    # Forward as enriched event in addition to legacy message field
    # Emit final event (image path implies single-shot completion)
    yield AssistantResponse(content=content, thinking=thinking, final=True)


DispatchQueueItem = DispatchEvent


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
    # Bridge published events via a local queue; TaskGroup provides structured
    # concurrency so we do not need a sentinel or explicit done_event.
    queue: asyncio.Queue[DispatchQueueItem] = asyncio.Queue()

    async def _queue_handler(evt: DispatchEvent) -> None:
        try:
            await queue.put(evt)
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Failed to enqueue AssistantResponse in message handler")

    def _sanitize_dispatch_event(evt: DispatchEvent) -> AssistantResponse:
        payload = evt.payload
        if evt.depth > 0 and payload.content:
            payload = payload.model_copy(update={"content": ""})
        # Ensure non-final events default to final=False instead of None.
        if payload.final is None:
            payload = payload.model_copy(update={"final": False})
        return payload

    try:
        async with event_context(handler=_queue_handler, context_id="root"):
            if data and len(data) > 0:
                async for event in _handle_image_message(message, data):
                    yield event
                return

            _message_history.append({"role": "user", "content": message})
            agent = computron
            _insert_system_message(agent)
            log_before_model_call = make_log_before_model_call(agent)
            log_after_model_call = make_log_after_model_call(agent)

            async def _producer() -> None:
                async for _context, _thinking in run_tool_call_loop(
                    messages=_message_history,
                    tools=agent.tools,
                    model=agent.model,
                    think=agent.think,
                    model_options=agent.options,
                    before_model_callbacks=[log_before_model_call],
                    after_model_callbacks=[log_after_model_call],
                ):
                    # Discard yielded tuple; authoritative stream is published events
                    pass

            # Structured concurrency: ensure producer completion or cancellation
            async with asyncio.TaskGroup() as tg:
                producer_task = tg.create_task(_producer())

                # Phase 1: Consume events concurrently while producer runs.
                while not producer_task.done():
                    item = await queue.get()
                    if not isinstance(item, DispatchEvent):  # pragma: no cover
                        logger.warning("Unexpected queue item type: %s", type(item))
                        continue
                    yield _sanitize_dispatch_event(item)

                # Phase 2: Producer finished (may have queued trailing events). Drain remaining.
                while not queue.empty():
                    item = await queue.get()
                    if not isinstance(item, DispatchEvent):  # pragma: no cover
                        logger.warning("Unexpected queue item type during drain: %s", type(item))
                        continue
                    yield _sanitize_dispatch_event(item)

    except Exception:
        logger.exception("Error handling user message")
        yield AssistantResponse(
            content="An error occurred while processing your message.",
            thinking=None,
            final=True,
        )
