"""High-level turn executor: wraps the agent loop with context management,
skill state, hooks, and optional caller-supplied persistence and prompt
augmentation.

The caller builds the ``Agent``, creates a ``Conversation``, optionally
provides a ``TurnPersistence`` and a ``SystemPromptBuilder``, then iterates
the yielded events.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, Callable, Iterable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol

from agents.types import Agent
from sdk.context._history import ConversationHistory
from sdk.context._manager import ContextManager
from sdk.context._strategy import LLMCompactionStrategy
from sdk.events._context import agent_span, get_current_dispatcher
from sdk.events._models import AgentEvent
from sdk.hooks._agent_event_buffer import AgentEventBufferHook
from sdk.hooks._default import default_hooks
from sdk.hooks._persistence import PersistenceHook
from sdk.skills import AgentState, get_skill
from sdk.tools._core import get_core_tools
from sdk.turn._execution import run_turn
from sdk.turn._turn import StopRequestedError, turn_scope

logger = logging.getLogger(__name__)

# Background tasks held to prevent GC; cleared via done callback.
_background_tasks: set[asyncio.Task] = set()


@dataclass
class Conversation:
    """Per-conversation state owned by the caller.

    Attributes:
        id: Unique conversation identifier.
        history: The conversation history.
    """

    id: str
    history: ConversationHistory


class TurnPersistence(Protocol):
    """Optional persistence hooks invoked by ``TurnExecutor``.

    Channels that don't want persistence pass ``None`` instead of an
    implementation. Implementations are typically thin wrappers over the
    application's on-disk store.
    """

    def load_skills(self, conversation_id: str) -> Iterable[str]:
        """Return persisted skill names to restore for this conversation."""

    def save_skills(self, conversation_id: str, skills: Iterable[str]) -> None:
        """Persist the set of currently-loaded skill names."""

    def save_events(
        self,
        conversation_id: str,
        events: list[AgentEvent],
    ) -> None:
        """Persist agent lifecycle events captured during the turn."""

    async def on_new_conversation(
        self,
        conversation_id: str,
        first_message: str,
    ) -> None:
        """Hook fired once when a conversation runs its first turn.

        Typical use: generate and persist a conversation title.
        """


SystemPromptBuilder = Callable[[], str]
"""Caller-supplied function returning the base system prompt for this turn.

Called fresh each turn so the caller can inject up-to-date state (e.g. a
memory block). If absent, the agent's ``instruction`` is used as-is.
"""


class TurnExecutor:
    """Executes a single agent turn with setup, hooks, and persistence.

    Callers build the ``Agent`` themselves and supply optional persistence
    and prompt-building injection points. The executor is stateless and
    safe to share across conversations.
    """

    async def execute(
        self,
        *,
        conversation: Conversation,
        agent: Agent,
        user_content: str,
        is_new_conversation: bool = False,
        preloaded_skills: Sequence[str] = (),
        persistence: TurnPersistence | None = None,
        build_system_prompt: SystemPromptBuilder | None = None,
        profile_name: str | None = None,
        sub_agent_name: str | None = None,
        sub_agent_id: str | None = None,
        correlation_id: str | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Run a single turn and yield events.

        Args:
            conversation: Per-conversation state.
            agent: The fully-constructed Agent to run.
            user_content: The user's message, already augmented if needed.
            is_new_conversation: True if this is the conversation's first
                turn. Triggers ``persistence.on_new_conversation`` when set;
                a no-op without a persistence implementation.
            preloaded_skills: Skill names to install before turn start
                (e.g. profile-attached skills).
            persistence: Optional persistence bundle. ``None`` skips all
                persistence calls.
            build_system_prompt: Optional callable returning the base system
                prompt; re-evaluated each turn so callers can inject
                up-to-date state (e.g. a memory block). Falls back to
                ``agent.instruction`` when ``None``.
            profile_name: Optional metadata threaded through ``agent_span``.
            sub_agent_name: When this turn is a sub-agent invocation, the
                short uppercase agent name. Forwarded to ``PersistenceHook``
                so the turn writes to the conversation's ``sub_agents/``
                directory instead of overwriting the main history.
            sub_agent_id: When this turn is a sub-agent invocation, a short
                unique id (UUID hex prefix). Pairs with ``sub_agent_name``.
            correlation_id: Optional id linking this turn to a prior
                ``SpawnRequestedPayload`` event so the UI can anchor a card
                to the request and attach the child agent to it.

        Yields:
            AgentEvent: Events emitted by the agent during the turn.
        """
        conv_id = conversation.id
        logger.info(
            "Turn started: conv=%s agent=%s message=%.80s",
            conv_id,
            agent.name,
            user_content,
        )

        # Fresh AgentState each turn; pre-load profile skills then restore
        # any persisted skills from a previous turn.
        agent_state = AgentState(await get_core_tools() + agent.tools)
        for skill_name in preloaded_skills:
            skill = get_skill(skill_name)
            if skill is None:
                logger.warning(
                    "Preloaded skill '%s' not registered; skipping", skill_name,
                )
                continue
            agent_state.add(skill)
            logger.info("Preloaded skill '%s' for conv=%s", skill_name, conv_id)

        if persistence is not None:
            for skill_name in persistence.load_skills(conv_id):
                if skill_name in agent_state.loaded_skill_names:
                    continue
                skill = get_skill(skill_name)
                if skill is None:
                    logger.warning(
                        "Persisted skill '%s' for conv=%s not found in registry; skipping",
                        skill_name,
                        conv_id,
                    )
                    continue
                agent_state.add(skill)
                logger.info("Restored skill '%s' for conv=%s", skill_name, conv_id)

        # Fresh ContextManager per turn — it borrows the live agent_state so
        # the token estimate reflects the current tool set, and the strategy
        # threshold tracks the agent's compaction setting.
        ctx_manager = ContextManager(
            history=conversation.history,
            agent_state=agent_state,
            context_limit=agent.context_window,
            agent_name=agent.name,
            compaction_threshold=agent.compaction_threshold,
            strategies=[
                LLMCompactionStrategy(threshold=agent.compaction_threshold),
            ],
        )

        # Bridge published events through a queue so we can yield them
        # regardless of how the caller is iterating.
        queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()

        async def _queue_handler(evt: AgentEvent) -> None:
            try:
                await queue.put(evt)
            except Exception:  # pragma: no cover - defensive
                logger.exception("Failed to enqueue AgentEvent in TurnExecutor")

        async def _producer() -> None:
            try:
                async with turn_scope(
                    handler=_queue_handler,
                    conversation_id=conv_id,
                ):
                    event_buffer = AgentEventBufferHook()
                    dispatcher = get_current_dispatcher()
                    if dispatcher:
                        dispatcher.subscribe(event_buffer.handle_event)

                    async with agent_span(
                        agent.name,
                        instruction=user_content,
                        agent_state=agent_state,
                        profile_name=profile_name,
                        correlation_id=correlation_id,
                    ):
                        conversation.history.append(
                            {"role": "user", "content": user_content},
                        )

                        base_prompt = (
                            build_system_prompt()
                            if build_system_prompt is not None
                            else agent.instruction
                        )
                        skill_prompt = agent_state.build_skill_prompt()
                        full_prompt = (
                            f"{base_prompt}\n{skill_prompt}"
                            if skill_prompt
                            else base_prompt
                        )
                        conversation.history.set_system_message(full_prompt)

                        hooks = default_hooks(
                            agent,
                            max_iterations=agent.max_iterations,
                            ctx_manager=ctx_manager,
                        )
                        hooks.append(
                            PersistenceHook(
                                conversation_id=conv_id,
                                history=conversation.history,
                                sub_agent_name=sub_agent_name,
                                sub_agent_id=sub_agent_id,
                            ),
                        )

                        with suppress(StopRequestedError):
                            await run_turn(
                                history=conversation.history,
                                agent=agent,
                                hooks=hooks,
                            )

                    if persistence is not None and agent_state.loaded_skill_names:
                        try:
                            persistence.save_skills(
                                conv_id,
                                agent_state.loaded_skill_names,
                            )
                        except Exception:
                            logger.exception(
                                "Failed to save loaded skills for '%s'", conv_id,
                            )

                    # Yield once so synchronous handlers registered via
                    # call_soon get to run before we read the buffer.
                    await asyncio.sleep(0)

                    if persistence is not None:
                        buffered_events = event_buffer.get_events()
                        if buffered_events:
                            try:
                                persistence.save_events(conv_id, buffered_events)
                                logger.info(
                                    "Saved %d agent events for conv=%s",
                                    len(buffered_events),
                                    conv_id,
                                )
                            except Exception:
                                logger.exception(
                                    "Failed to save agent events for '%s'", conv_id,
                                )

                    if is_new_conversation and persistence is not None:
                        task = asyncio.create_task(
                            persistence.on_new_conversation(conv_id, user_content),
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
