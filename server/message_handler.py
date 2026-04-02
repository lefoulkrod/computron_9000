"""Message handler for user prompts."""

import asyncio
import logging
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field

from sdk.context import ContextManager, ConversationHistory, LLMCompactionStrategy, ToolClearingStrategy
from sdk.events import (
    AgentEvent,
    ContentPayload,
    TurnEndPayload,
    agent_span,
    get_current_dispatcher,
    set_model_options,
)
from sdk.providers import get_provider
from sdk.turn import turn_scope
from agents.types import Agent, Data, LLMOptions
from tools.memory import load_memory
from tools.virtual_computer.receive_file import receive_attachment

from agents.computron import (
    DESCRIPTION as _COMPUTRON_DESCRIPTION,
    NAME as _COMPUTRON_NAME,
    SYSTEM_PROMPT as _COMPUTRON_PROMPT,
    TOOLS as _COMPUTRON_TOOLS,
)
from agents.browser import (
    DESCRIPTION as _BROWSER_DESCRIPTION,
    NAME as _BROWSER_NAME,
    SYSTEM_PROMPT as _BROWSER_PROMPT,
    TOOLS as _BROWSER_TOOLS,
)
from agents.coding import (
    DESCRIPTION as _CODER_DESCRIPTION,
    NAME as _CODER_NAME,
    SYSTEM_PROMPT as _CODER_PROMPT,
    TOOLS as _CODER_TOOLS,
)
from agents.desktop import (
    DESCRIPTION as _DESKTOP_DESCRIPTION,
    NAME as _DESKTOP_NAME,
    SYSTEM_PROMPT as _DESKTOP_PROMPT,
    TOOLS as _DESKTOP_TOOLS,
)
from config import load_config
from conversations import (
    generate_conversation_title,
    load_conversation_history,
    save_agent_events,
    save_conversation_title,
)
from sdk import (
    PersistenceHook,
    default_hooks,
    run_turn,
)
from sdk.hooks._agent_event_buffer import AgentEventBufferHook
from sdk.turn._turn import StopRequestedError

# Agent registry mapping user-facing IDs to their config constants.
_AGENT_REGISTRY: dict[str, tuple[str, str, str, list]] = {
    "computron": (_COMPUTRON_NAME, _COMPUTRON_DESCRIPTION, _COMPUTRON_PROMPT, _COMPUTRON_TOOLS),
    "browser": (_BROWSER_NAME, _BROWSER_DESCRIPTION, _BROWSER_PROMPT, _BROWSER_TOOLS),
    "coder": (_CODER_NAME, _CODER_DESCRIPTION, _CODER_PROMPT, _CODER_TOOLS),
    "desktop": (_DESKTOP_NAME, _DESKTOP_DESCRIPTION, _DESKTOP_PROMPT, _DESKTOP_TOOLS),
}

# Aliases for convenience (e.g. "computer" -> "coder")
_AGENT_ALIASES: dict[str, str] = {
    "computer": "coder",
}

AVAILABLE_AGENTS = sorted(_AGENT_REGISTRY.keys())


def _resolve_agent(agent_id: str | None) -> tuple[str, str, str, list]:
    """Resolve an agent ID to its config tuple, defaulting to computron."""
    if not agent_id:
        return _AGENT_REGISTRY["computron"]
    key = _AGENT_ALIASES.get(agent_id, agent_id)
    return _AGENT_REGISTRY.get(key, _AGENT_REGISTRY["computron"])

logger = logging.getLogger(__name__)

_DEFAULT_CONVERSATION_ID = "default"


@dataclass
class _Conversation:
    """Per-conversation state: conversation history and context manager."""

    history: ConversationHistory = field(default_factory=ConversationHistory)
    context_manager: ContextManager | None = None


# Conversation store keyed by conversation ID.
_conversations: dict[str, _Conversation] = {}


def _get_conversation(conversation_id: str | None = None) -> _Conversation:
    """Return the conversation for the given ID, creating one if needed."""
    cid = conversation_id or _DEFAULT_CONVERSATION_ID
    if cid not in _conversations:
        _conversations[cid] = _Conversation(
            history=ConversationHistory(instance_id=cid),
        )
    return _conversations[cid]


def reset_message_history(conversation_id: str | None = None) -> None:
    """Resets the conversation history and context manager."""
    cid = conversation_id or _DEFAULT_CONVERSATION_ID
    _conversations.pop(cid, None)


def resume_conversation(conversation_id: str) -> list[dict] | None:
    """Load a conversation's full-fidelity history and install it.

    Returns the raw messages for the UI to display, or None if not found.
    """
    messages = load_conversation_history(conversation_id)
    if messages is None:
        return None

    conversation = _Conversation(
        history=ConversationHistory(messages, instance_id=conversation_id),
    )
    _conversations[conversation_id] = conversation
    return messages


def _refresh_system_message(history: ConversationHistory, system_prompt: str) -> None:
    """Re-inserts the system message at the start of history with up-to-date memory.

    Called before each model invocation so any memories stored during the previous
    turn are visible immediately.
    """
    instruction = system_prompt
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


def _build_agent(agent_id: str | None, options: LLMOptions) -> Agent:
    """Construct an Agent from a registry ID and LLM options."""
    agent_name, agent_desc, agent_prompt, agent_tools = _resolve_agent(agent_id)
    return Agent(
        name=agent_name,
        description=agent_desc,
        instruction=agent_prompt,
        tools=agent_tools,
        model=options.model,  # type: ignore[arg-type]  # validated by caller
        think=options.think or False,
        persist_thinking=options.persist_thinking if options.persist_thinking is not None else True,
        options=options.to_options(),
        max_iterations=options.max_iterations or 0,
    )


def _ensure_context_manager(
    conversation: _Conversation,
    active_agent: Agent,
) -> ContextManager:
    """Return the conversation's context manager, creating it if needed."""
    if conversation.context_manager is None:
        num_ctx = active_agent.options.get("num_ctx", 0) if active_agent.options else 0
        conversation.context_manager = ContextManager(
            history=conversation.history,
            context_limit=num_ctx,
            agent_name=active_agent.name,
            strategies=[ToolClearingStrategy(), LLMCompactionStrategy()],
        )
    return conversation.context_manager


async def _run_turn(
    *,
    conversation: _Conversation,
    active_agent: Agent,
    user_content: str,
    options: LLMOptions,
    conversation_id: str | None,
    handler: Callable[[AgentEvent], object],
) -> None:
    """Execute a single conversation turn: model calls, tool execution, persistence."""
    logger.info(
        "Turn started: conv=%s agent=%s message=%.80s",
        conversation_id or _DEFAULT_CONVERSATION_ID,
        active_agent.name,
        user_content,
    )
    set_model_options(options)

    ctx_manager = _ensure_context_manager(conversation, active_agent)
    conv_id = conversation_id or _DEFAULT_CONVERSATION_ID

    async with turn_scope(handler=handler, conversation_id=conversation_id):
        # Subscribe event buffer to capture agent lifecycle/preview events
        event_buffer = AgentEventBufferHook()
        dispatcher = get_current_dispatcher()
        if dispatcher:
            dispatcher.subscribe(event_buffer.handle_event)

        with agent_span(active_agent.name, instruction=user_content):
            conversation.history.append({"role": "user", "content": user_content})
            _refresh_system_message(conversation.history, active_agent.instruction)

            hooks = default_hooks(
                active_agent,
                max_iterations=active_agent.max_iterations,
                ctx_manager=ctx_manager,
            )

            hooks.append(PersistenceHook(
                conversation_id=conv_id,
                history=conversation.history,
            ))

            with suppress(StopRequestedError):
                await run_turn(
                    history=conversation.history,
                    agent=active_agent,
                    hooks=hooks,
                )

        # Yield to event loop so call_soon callbacks (sync event handlers)
        # have a chance to run before we read the buffer
        await asyncio.sleep(0)

        # Save agent events after the turn (outside agent_span so completion is captured)
        buffered_events = event_buffer.get_events()
        if buffered_events:
            try:
                save_agent_events(conv_id, buffered_events)
                logger.info("Saved %d agent events for conv=%s", len(buffered_events), conv_id)
            except Exception:
                logger.exception("Failed to save agent events for '%s'", conv_id)


async def _generate_title_if_first_turn(conversation_id: str) -> None:
    """Generate title if this is the first turn of the conversation."""
    try:
        history = load_conversation_history(conversation_id)
        if not history:
            return

        user_msgs = [m for m in history if m.get("role") == "user"]
        # Only generate if exactly 1 user message (first turn)
        if len(user_msgs) != 1:
            return

        first_msg = user_msgs[0].get("content", "")
        if not first_msg:
            return

        # Generate and save title
        title = await generate_conversation_title(first_msg)
        save_conversation_title(conversation_id, title)
        logger.info("Generated title for conversation %s: %r", conversation_id, title)
    except Exception:
        logger.exception("Failed to generate title for conversation %s", conversation_id)


async def handle_user_message(
    message: str,
    data: Sequence[Data] | None = None,
    *,
    options: LLMOptions,
    conversation_id: str | None = None,
    agent: str | None = None,
) -> AsyncGenerator[AgentEvent, None]:
    """Handles a user message by sending it to the LLM and yielding events.

    Args:
        message: The user's message.
        data: Optional sequence of file attachment data.
        options: LLM inference options for this turn.
        conversation_id: Optional conversation identifier for isolation.
        agent: Optional agent identifier to use for this turn.

    Yields:
        AgentEvent: Events from the LLM.
    """
    conversation = _get_conversation(conversation_id)

    user_content = message
    if data:
        user_content = _augment_message_with_attachments(message, data)

    if not options.model:
        msg = "No model specified. The UI must send a model in the request options."
        raise ValueError(msg)

    try:
        # Bridge published events via a queue so we can stream them to the caller.
        queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()

        async def _queue_handler(evt: AgentEvent) -> None:
            try:
                await queue.put(evt)
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Failed to enqueue AgentEvent in message handler")

        active_agent = _build_agent(agent, options)

        async def _producer() -> None:
            try:
                await _run_turn(
                    conversation=conversation,
                    active_agent=active_agent,
                    user_content=user_content,
                    options=options,
                    conversation_id=conversation_id,
                    handler=_queue_handler,
                )
            finally:
                await queue.put(None)

        producer_task = asyncio.create_task(_producer())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            if not producer_task.done():
                producer_task.cancel()
            with suppress(Exception):
                await producer_task

    except Exception:
        logger.exception("Error handling user message")
        yield AgentEvent(payload=ContentPayload(
            type="content",
            content="An error occurred while processing your message.",
        ))
        yield AgentEvent(payload=TurnEndPayload(type="turn_end"))
    finally:
        # After turn completes, kick off title generation if first turn (fire-and-forget)
        if conversation_id:
            asyncio.create_task(_generate_title_if_first_turn(conversation_id))
