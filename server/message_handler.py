"""Message handler for user prompts."""

import asyncio
import logging
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from agents import (
    AgentProfile,
    build_agent,
    get_agent_profile,
)
from agents.types import Agent, Data
from conversations import (
    generate_conversation_title,
    load_conversation_history,
    load_loaded_skills,
    save_agent_events,
    save_conversation_title,
    save_loaded_skills,
)
from sdk import (
    PersistenceHook,
    default_hooks,
    run_turn,
)
from sdk.context import ContextManager, ConversationHistory, LLMCompactionStrategy, ToolClearingStrategy
from sdk.events import (
    AgentEvent,
    ContentPayload,
    TurnEndPayload,
    agent_span,
    get_current_dispatcher,
)
from sdk.hooks._agent_event_buffer import AgentEventBufferHook
from sdk.skills import AgentState, get_skill
from sdk.tools._core import get_core_tools
from sdk.turn import turn_scope
from sdk.turn._turn import StopRequestedError
from tools.memory import load_memory
from tools.virtual_computer.receive_file import receive_attachment

logger = logging.getLogger(__name__)
_console = Console(stderr=True)

_DEFAULT_CONVERSATION_ID = "default"


def _log_turn_start(profile: AgentProfile) -> None:
    """Print a Rich panel showing the active profile and its settings."""
    body = Text()
    body.append("profile: ", style="bold")
    body.append(profile.name, style="bright_magenta")
    body.append(f" ({profile.id})", style="dim")
    body.append("\nmodel:   ", style="bold")
    body.append(profile.model or "—", style="bright_yellow")
    if profile.skills:
        body.append("\nskills:  ", style="bold")
        body.append(", ".join(profile.skills), style="bright_cyan")
    params = []
    if profile.temperature is not None:
        params.append(f"temp={profile.temperature}")
    if profile.top_k is not None:
        params.append(f"top_k={profile.top_k}")
    if profile.top_p is not None:
        params.append(f"top_p={profile.top_p}")
    if profile.think:
        params.append("think")
    if profile.num_ctx is not None:
        params.append(f"ctx={profile.num_ctx}")
    if profile.max_iterations is not None:
        params.append(f"max_iter={profile.max_iterations}")
    if params:
        body.append("\nparams:  ", style="bold")
        body.append(", ".join(params), style="dim")

    _console.print(
        Panel(
            body,
            title="[bold bright_magenta]🤖 Agent Turn[/bold bright_magenta]",
            border_style="bright_magenta",
            expand=False,
        )
    )


@dataclass
class _Conversation:
    """Per-conversation state: conversation history and context manager."""

    history: ConversationHistory = field(default_factory=ConversationHistory)
    context_manager: ContextManager | None = None


# Conversation store keyed by conversation ID.
_conversations: dict[str, _Conversation] = {}

# Track background tasks to avoid garbage collection (RUF006)
_background_tasks: set[asyncio.Task] = set()


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
    return f"{message}\n\n[Attached files written to virtual computer]\n{files_block}"


def _build_agent_from_profile(profile: AgentProfile) -> Agent:
    """Construct an Agent from an AgentProfile."""
    from tools.memory import forget, remember
    from tools.virtual_computer.run_bash_cmd import run_bash_cmd

    return build_agent(profile, tools=[run_bash_cmd, remember, forget])


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
    profile: AgentProfile,
    user_content: str,
    conversation_id: str | None,
    handler: Callable[[AgentEvent], object],
    is_new_conversation: bool = False,
) -> None:
    """Execute a single conversation turn: model calls, tool execution, persistence."""
    logger.info(
        "Turn started: conv=%s agent=%s message=%.80s",
        conversation_id or _DEFAULT_CONVERSATION_ID,
        active_agent.name,
        user_content,
    )
    _log_turn_start(profile)

    ctx_manager = _ensure_context_manager(conversation, active_agent)
    conv_id = conversation_id or _DEFAULT_CONVERSATION_ID

    # Fresh AgentState each turn, restored from persisted skill names.
    # Pre-load skills from the profile.
    agent_state = AgentState(get_core_tools() + active_agent.tools)
    for skill_name in profile.skills:
        skill = get_skill(skill_name)
        if skill is None:
            logger.warning("Profile skill '%s' not registered; skipping", skill_name)
            continue
        agent_state.add(skill)
        logger.info("Pre-loaded profile skill '%s' for conv=%s", skill_name, conv_id)
    for skill_name in load_loaded_skills(conv_id):
        if skill_name in agent_state.loaded_skill_names:
            continue
        skill = get_skill(skill_name)
        if skill is None:
            logger.warning(
                "Persisted skill '%s' for conv=%s was not found in the skills registry; skipping",
                skill_name,
                conv_id,
            )
            continue
        agent_state.add(skill)
        logger.info("Restored skill '%s' for conv=%s", skill_name, conv_id)

    async with turn_scope(handler=handler, conversation_id=conversation_id):
        # Subscribe event buffer to capture agent lifecycle/preview events
        event_buffer = AgentEventBufferHook()
        dispatcher = get_current_dispatcher()
        if dispatcher:
            dispatcher.subscribe(event_buffer.handle_event)

        async with agent_span(
            active_agent.name, instruction=user_content, agent_state=agent_state, profile_name=profile.name
        ):
            conversation.history.append({"role": "user", "content": user_content})
            # Build full system prompt: profile prompt + loaded skill prompts
            full_prompt = active_agent.instruction
            skill_prompt = agent_state.build_skill_prompt()
            if skill_prompt:
                full_prompt = full_prompt + "\n" + skill_prompt
            _refresh_system_message(conversation.history, full_prompt)

            hooks = default_hooks(
                active_agent,
                max_iterations=active_agent.max_iterations,
                ctx_manager=ctx_manager,
            )

            hooks.append(
                PersistenceHook(
                    conversation_id=conv_id,
                    history=conversation.history,
                )
            )

            with suppress(StopRequestedError):
                await run_turn(
                    history=conversation.history,
                    agent=active_agent,
                    hooks=hooks,
                )

        # Persist loaded skills so they survive across turns and restarts
        if agent_state.loaded_skill_names:
            try:
                save_loaded_skills(conv_id, agent_state.loaded_skill_names)
            except Exception:
                logger.exception("Failed to save loaded skills for '%s'", conv_id)

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

        # Generate a title for new conversations after the first successful turn
        if is_new_conversation and conversation_id:
            task = asyncio.create_task(_generate_title(conversation_id, user_content))
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)


async def _generate_title(conversation_id: str, first_message: str) -> None:
    """Generate and save a title for a new conversation."""
    try:
        title = await generate_conversation_title(first_message)
        save_conversation_title(conversation_id, title)
        logger.info("Generated title for conversation %s: %r", conversation_id, title)
    except Exception:
        logger.exception("Failed to generate title for conversation %s", conversation_id)


async def handle_user_message(
    message: str,
    data: Sequence[Data] | None = None,
    *,
    profile_id: str | None = None,
    conversation_id: str | None = None,
) -> AsyncGenerator[AgentEvent, None]:
    """Handles a user message by sending it to the LLM and yielding events.

    Args:
        message: The user's message.
        data: Optional sequence of file attachment data.
        profile_id: Agent profile to use. Falls back to Computron default.
        conversation_id: Optional conversation identifier for isolation.

    Yields:
        AgentEvent: Events from the LLM.
    """
    cid = conversation_id or _DEFAULT_CONVERSATION_ID
    is_new_conversation = cid not in _conversations
    conversation = _get_conversation(conversation_id)

    user_content = message
    if data:
        user_content = _augment_message_with_attachments(message, data)

    if not profile_id:
        msg = "profile_id is required"
        raise RuntimeError(msg)
    profile = get_agent_profile(profile_id)
    if profile is None:
        msg = f"Agent profile '{profile_id}' not found"
        raise RuntimeError(msg)

    if not profile.model:
        msg = "No model configured. Complete the setup wizard to select a model."
        raise ValueError(msg)

    try:
        # Bridge published events via a queue so we can stream them to the caller.
        queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()

        async def _queue_handler(evt: AgentEvent) -> None:
            try:
                await queue.put(evt)
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Failed to enqueue AgentEvent in message handler")

        active_agent = _build_agent_from_profile(profile)

        async def _producer() -> None:
            try:
                await _run_turn(
                    conversation=conversation,
                    active_agent=active_agent,
                    profile=profile,
                    user_content=user_content,
                    conversation_id=conversation_id,
                    handler=_queue_handler,
                    is_new_conversation=is_new_conversation,
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
        yield AgentEvent(
            payload=ContentPayload(
                type="content",
                content="An error occurred while processing your message.",
            )
        )
        yield AgentEvent(payload=TurnEndPayload(type="turn_end"))
