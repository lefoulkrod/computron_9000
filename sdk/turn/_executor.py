"""Single-turn agent driver.

Given a fully-wired ``Conversation`` (with ``agent_state`` populated)
and an ``Agent``, drives one turn: opens the turn/agent spans, appends
the user message, composes the system prompt with the skill block,
runs the agent loop, and yields events to the caller.

Per-conversation lifecycle work — hydrating ``agent_state`` from disk,
saving events, flushing skills, firing first-turn hooks — is the
caller's responsibility, not the executor's. See the channels (web /
telegram) and one-shot callers (TaskExecutor, ``spawn_agent``) for the
two shapes that lifecycle takes.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import suppress

from agents.types import Agent
from sdk.context._manager import ContextManager
from sdk.context._strategy import LLMCompactionStrategy
from sdk.events._context import agent_span
from sdk.events._models import AgentEvent
from sdk.hooks._default import default_hooks
from sdk.hooks._persistence import PersistenceHook
from sdk.turn._conversation import Conversation
from sdk.turn._execution import run_turn
from sdk.turn._turn import StopRequestedError, turn_scope

logger = logging.getLogger(__name__)


class TurnExecutor:
    """Drives a single agent turn against a pre-wired ``Conversation``.

    Stateless and safe to share across conversations.
    """

    async def execute(
        self,
        *,
        conversation: Conversation,
        agent: Agent,
        user_content: str,
        profile_name: str | None = None,
        sub_agent_name: str | None = None,
        sub_agent_id: str | None = None,
        correlation_id: str | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Run a single turn and yield events.

        Args:
            conversation: Per-conversation state. ``conversation.agent_state``
                must be populated before calling — callers hydrate it from
                disk on cache miss or build it inline for one-shot turns.
            agent: The fully-constructed ``Agent`` to run.
            user_content: The user's message, already augmented if needed.
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
        if conversation.agent_state is None:
            msg = (
                f"Conversation {conversation.id!r} has no agent_state; "
                "caller must populate it before running a turn."
            )
            raise ValueError(msg)

        conv_id = conversation.id
        agent_state = conversation.agent_state
        logger.info(
            "Turn started: conv=%s agent=%s message=%.80s",
            conv_id,
            agent.name,
            user_content,
        )

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

                        skill_prompt = agent_state.build_skill_prompt()
                        full_prompt = (
                            f"{agent.instruction}\n{skill_prompt}"
                            if skill_prompt
                            else agent.instruction
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
