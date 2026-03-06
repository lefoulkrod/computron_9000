"""Message handler for user prompts."""

import asyncio
import logging
from collections.abc import AsyncGenerator, Sequence
from contextlib import suppress

from agents.ollama.sdk.context import ContextManager, ConversationHistory
from agents.ollama.sdk.events import (
    AssistantResponse,
    agent_span,
    event_context,
    set_model_options,
)
from agents.types import Agent, Data, LLMOptions
from config import load_config
from tools.memory import load_memory
from tools.virtual_computer.receive_file import receive_attachment

from .computron import DESCRIPTION, NAME, SYSTEM_PROMPT, TOOLS
from .sdk import (
    make_log_after_model_call,
    make_log_before_model_call,
    run_tool_call_loop,
)

logger = logging.getLogger(__name__)

config = load_config()

# Module-level conversation history and context manager for the chat session.
_history = ConversationHistory()
_context_manager: ContextManager | None = None


def reset_message_history() -> None:
    """Resets the conversation history and context manager."""
    global _context_manager
    _history.clear()
    _context_manager = None


def _refresh_system_message() -> None:
    """Re-inserts the system message at the start of history with up-to-date memory.

    Called before each model invocation so any memories stored during the previous
    turn are visible immediately.
    """
    instruction = SYSTEM_PROMPT
    memory = load_memory()
    if memory:
        lines = "\n".join(f"  {k}: {e.value}" for k, e in memory.items())
        sep = "─" * 64
        memory_block = f"\n── Memory (persisted across sessions) ──────────────────────────\n{lines}\n{sep}\n"
        instruction = memory_block + instruction

    _history.set_system_message(instruction)


def _augment_message_with_attachments(message: str, data: Sequence[Data]) -> str:
    """Write attachments to the virtual computer and return an augmented message."""
    file_lines = []
    for d in data:
        container_path = receive_attachment(
            base64_encoded=d.base64_encoded,
            content_type=d.content_type,
            filename=d.filename,
        )
        name = d.filename or "unnamed"
        file_lines.append(f"  - {name} ({d.content_type}) -> {container_path}")

    files_block = "\n".join(file_lines)
    return (
        f"{message}\n\n"
        f"[Attached files written to virtual computer]\n"
        f"{files_block}"
    )


async def handle_user_message(
    message: str,
    data: Sequence[Data] | None = None,
    *,
    options: LLMOptions | None = None,
) -> AsyncGenerator[AssistantResponse, None]:
    """Handles a user message by sending it to the LLM and yielding events.

    Args:
        message: The user's message.
        data: Optional sequence of file attachment data.
        options: LLM inference options for this turn.

    Yields:
        AssistantResponse: Events from the LLM.
    """
    # Write any attachments to the virtual computer and augment the message
    # with file paths so the agent can access them via tools.
    user_content = message
    if data:
        user_content = _augment_message_with_attachments(message, data)

    # Resolve default model once so all downstream consumers (sub-agents,
    # agent tools) inherit the resolved value via set_model_options.
    if options is None:
        options = LLMOptions()
    if not options.model:
        options.model = config.get_default_model().model
    try:
        # Bridge published events via a local queue so we can stream results to the caller.
        queue: asyncio.Queue[AssistantResponse | None] = asyncio.Queue()

        async def _queue_handler(evt: AssistantResponse) -> None:
            try:
                await queue.put(evt)
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Failed to enqueue AssistantResponse in message handler")

        async def _producer() -> None:
            global _context_manager
            agent = Agent(
                name=NAME,
                description=DESCRIPTION,
                instruction=SYSTEM_PROMPT,
                tools=TOOLS,
                model=options.model,  # type: ignore[arg-type]  # resolved above
                think=options.think or False,
                persist_thinking=options.persist_thinking if options.persist_thinking is not None else True,
                options=options.to_ollama_options(),
                max_iterations=options.max_iterations or 0,
            )
            # Propagate options to sub-agents via context vars
            set_model_options(options)

            # Lazily create the context manager with the model's context limit.
            if _context_manager is None:
                num_ctx = agent.options.get("num_ctx", 0) if agent.options else 0
                _context_manager = ContextManager(
                    history=_history,
                    context_limit=num_ctx,
                )
            try:
                async with event_context(handler=_queue_handler):
                    with agent_span(agent.name):
                        _history.append({"role": "user", "content": user_content})
                        _refresh_system_message()
                        _context_manager.apply_strategies()
                        async for _, _ in run_tool_call_loop(
                            history=_history,
                            agent=agent,
                            before_model_callbacks=[make_log_before_model_call(agent)],
                            after_model_callbacks=[
                                make_log_after_model_call(agent),
                                _context_manager.make_after_model_callback(),
                            ],
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
