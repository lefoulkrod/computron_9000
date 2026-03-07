"""Message handler for user prompts."""

import asyncio
import logging
from collections.abc import AsyncGenerator, Sequence
from contextlib import suppress
from dataclasses import dataclass, field

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
    default_hooks,
    run_tool_call_loop,
)

logger = logging.getLogger(__name__)

config = load_config()

_DEFAULT_SESSION_ID = "default"


@dataclass
class _Session:
    """Per-session state: conversation history and context manager."""

    history: ConversationHistory = field(default_factory=ConversationHistory)
    context_manager: ContextManager | None = None


# Session store keyed by session ID.
_sessions: dict[str, _Session] = {}


def _get_session(session_id: str | None = None) -> _Session:
    """Return the session for the given ID, creating one if needed."""
    sid = session_id or _DEFAULT_SESSION_ID
    if sid not in _sessions:
        _sessions[sid] = _Session()
    return _sessions[sid]


def reset_message_history(session_id: str | None = None) -> None:
    """Resets the conversation history and context manager for a session."""
    sid = session_id or _DEFAULT_SESSION_ID
    _sessions.pop(sid, None)


def _refresh_system_message(history: ConversationHistory) -> None:
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

    history.set_system_message(instruction)


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
    session_id: str | None = None,
) -> AsyncGenerator[AssistantResponse, None]:
    """Handles a user message by sending it to the LLM and yielding events.

    Args:
        message: The user's message.
        data: Optional sequence of file attachment data.
        options: LLM inference options for this turn.
        session_id: Optional session identifier for conversation isolation.

    Yields:
        AssistantResponse: Events from the LLM.
    """
    session = _get_session(session_id)

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
            if session.context_manager is None:
                num_ctx = agent.options.get("num_ctx", 0) if agent.options else 0
                session.context_manager = ContextManager(
                    history=session.history,
                    context_limit=num_ctx,
                    agent_name=agent.name,
                )
            try:
                async with event_context(handler=_queue_handler, session_id=session_id):
                    with agent_span(agent.name):
                        session.history.append({"role": "user", "content": user_content})
                        _refresh_system_message(session.history)
                        session.context_manager.apply_strategies()
                        hooks = default_hooks(
                            agent,
                            max_iterations=agent.max_iterations,
                            ctx_manager=session.context_manager,
                        )
                        async for _, _ in run_tool_call_loop(
                            history=session.history,
                            agent=agent,
                            hooks=hooks,
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
