"""High-level turn executor that encapsulates agent resolution, conversation
management, memory injection, skill restoration, hook wiring, and persistence.

Channels (SSE, Telegram, future) own conversation lifecycle — they load from
disk to resume or create new for fresh starts — then call
``TurnExecutor.execute()`` with a ``Conversation`` object.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from agents import resolve_agent as _resolve_agent
from agents.types import Agent, LLMOptions
from conversations import (
    generate_conversation_title,
    load_loaded_skills,
    save_agent_events,
    save_conversation_title,
    save_loaded_skills,
)
from sdk.context import (
    ContextManager,
    ConversationHistory,
    LLMCompactionStrategy,
    ToolClearingStrategy,
)
from sdk.events import (
    AgentEvent,
    agent_span,
    get_current_dispatcher,
    set_model_options,
)
from sdk.hooks._agent_event_buffer import AgentEventBufferHook
from sdk.skills.agent_state import AgentState
from sdk.tools._core import get_core_tools
from sdk.turn._turn import StopRequestedError, turn_scope
from tools.memory import load_memory

from sdk.hooks._default import default_hooks
from sdk.hooks._persistence import PersistenceHook

from ._execution import run_turn

logger = logging.getLogger(__name__)

# Track background tasks to avoid garbage collection (RUF006)
_background_tasks: set[asyncio.Task] = set()


@dataclass
class Conversation:
    """Per-conversation state owned by a channel.

    Channels create and own ``Conversation`` instances. They load from
    disk to resume or create new for fresh starts, then pass the
    ``Conversation`` to ``TurnExecutor.execute()``.

    Attributes:
        id: Unique conversation identifier.
        history: The conversation history.
        context_manager: Optional context manager for token tracking.
    """

    id: str
    history: ConversationHistory
    context_manager: ContextManager | None = None


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
        memory_block = (
            f"\n── Memory (persisted across sessions) "
            f"──────────────────────────────────────────\n{lines}\n{sep}\n"
        )
        instruction = memory_block + instruction

    history.set_system_message(instruction)


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
        persist_thinking=(
            options.persist_thinking if options.persist_thinking is not None else True
        ),
        options=options.to_options(),
        max_iterations=options.max_iterations or 0,
    )


def _ensure_context_manager(
    conversation: Conversation,
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


async def _generate_title(conversation_id: str, first_message: str) -> None:
    """Generate and save a title for a new conversation."""
    try:
        title = await generate_conversation_title(first_message)
        save_conversation_title(conversation_id, title)
        logger.info("Generated title for conversation %s: %r", conversation_id, title)
    except Exception:
        logger.exception("Failed to generate title for conversation %s", conversation_id)


class TurnExecutor:
    """Executes a single agent turn with all setup, hooks, and persistence.

    Channels create a ``Conversation``, call ``execute()``, and iterate
    the yielded events. The executor handles agent resolution, memory
    injection, skill restoration, hook wiring, and persistence.

    Usage::

        executor = TurnExecutor()
        conversation = Conversation(
            id="my_conv",
            history=ConversationHistory(instance_id="my_conv"),
        )
        async for event in executor.execute(
            conversation=conversation,
            user_content="Hello!",
            agent_id="default",
            options=LLMOptions(model="llama3"),
        ):
            # handle event
            ...
    """

    async def execute(
        self,
        conversation: Conversation,
        user_content: str,
        *,
        agent_id: str | None = None,
        options: LLMOptions | None = None,
        is_new_conversation: bool = False,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Execute a single agent turn and yield events.

        Args:
            conversation: The conversation to execute the turn in.
            user_content: The user's message content (already augmented
                with any attachment info by the channel).
            agent_id: Optional agent identifier to use for this turn.
            options: LLM inference options. Must include a model.
            is_new_conversation: Whether this is a new conversation
                (triggers title generation).

        Yields:
            AgentEvent: Events from the agent during the turn.
        """
        if options is None or not options.model:
            msg = "No model specified. A model must be provided in options."
            raise ValueError(msg)

        conv_id = conversation.id
        active_agent = _build_agent(agent_id, options)

        logger.info(
            "Turn started: conv=%s agent=%s message=%.80s",
            conv_id,
            active_agent.name,
            user_content,
        )
        set_model_options(options)

        ctx_manager = _ensure_context_manager(conversation, active_agent)

        # Fresh AgentState each turn, restored from persisted skill names.
        agent_state = AgentState(get_core_tools() + active_agent.tools)
        for skill_name in load_loaded_skills(conv_id):
            if agent_state.load(skill_name) is not None:
                logger.info("Restored skill '%s' for conv=%s", skill_name, conv_id)

        # Bridge published events via a queue so we can stream them to
        # the caller regardless of channel.
        queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()

        async def _queue_handler(evt: AgentEvent) -> None:
            try:
                await queue.put(evt)
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Failed to enqueue AgentEvent in TurnExecutor")

        async def _producer() -> None:
            try:
                async with turn_scope(
                    handler=_queue_handler,
                    conversation_id=conv_id,
                ):
                    # Subscribe event buffer to capture agent lifecycle/preview events
                    event_buffer = AgentEventBufferHook()
                    dispatcher = get_current_dispatcher()
                    if dispatcher:
                        dispatcher.subscribe(event_buffer.handle_event)

                    with agent_span(
                        active_agent.name,
                        instruction=user_content,
                        agent_state=agent_state,
                    ):
                        conversation.history.append(
                            {"role": "user", "content": user_content},
                        )
                        _refresh_system_message(
                            conversation.history,
                            active_agent.instruction,
                        )

                        hooks = default_hooks(
                            active_agent,
                            max_iterations=active_agent.max_iterations,
                            ctx_manager=ctx_manager,
                        )

                        hooks.append(
                            PersistenceHook(
                                conversation_id=conv_id,
                                history=conversation.history,
                            ),
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
                            save_loaded_skills(
                                conv_id,
                                agent_state.loaded_skill_names,
                            )
                        except Exception:
                            logger.exception(
                                "Failed to save loaded skills for '%s'",
                                conv_id,
                            )

                    # Yield to event loop so call_soon callbacks (sync event
                    # handlers) have a chance to run before we read the buffer
                    await asyncio.sleep(0)

                    # Save agent events after the turn (outside agent_span so
                    # completion is captured)
                    buffered_events = event_buffer.get_events()
                    if buffered_events:
                        try:
                            save_agent_events(conv_id, buffered_events)
                            logger.info(
                                "Saved %d agent events for conv=%s",
                                len(buffered_events),
                                conv_id,
                            )
                        except Exception:
                            logger.exception(
                                "Failed to save agent events for '%s'",
                                conv_id,
                            )

                    # Generate a title for new conversations after the first
                    # successful turn
                    if is_new_conversation:
                        task = asyncio.create_task(
                            _generate_title(conv_id, user_content),
                        )
                        _background_tasks.add(task)
                        task.add_done_callback(_background_tasks.discard)
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