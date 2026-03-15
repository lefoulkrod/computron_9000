"""Message handler for user prompts."""

import asyncio
import logging
from collections.abc import AsyncGenerator, Sequence
from contextlib import suppress
from dataclasses import dataclass, field

from sdk.context import ContextManager, ConversationHistory, SummarizeStrategy
from sdk.events import (
    AssistantResponse,
    agent_span,
    get_sub_agent_histories,
    init_sub_agent_collector,
    set_model_options,
)
from sdk.loop import turn_scope
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
from conversations import save_conversation_history, save_sub_agent_histories, load_conversation_history
from sdk import (
    TurnRecorderHook,
    SkillTrackingHook,
    default_hooks,
    run_tool_call_loop,
)

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


def resume_session(conversation_id: str) -> list[dict] | None:
    """Load a conversation's full-fidelity history and install it as a session.

    Returns the raw messages for the UI to display, or None if not found.
    """
    messages = load_conversation_history(conversation_id)
    if messages is None:
        return None

    session = _Session(history=ConversationHistory(messages))
    _sessions[conversation_id] = session
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


async def handle_user_message(
    message: str,
    data: Sequence[Data] | None = None,
    *,
    options: LLMOptions | None = None,
    session_id: str | None = None,
    agent: str | None = None,
) -> AsyncGenerator[AssistantResponse, None]:
    """Handles a user message by sending it to the LLM and yielding events.

    Args:
        message: The user's message.
        data: Optional sequence of file attachment data.
        options: LLM inference options for this turn.
        session_id: Optional session identifier for conversation isolation.
        agent: Optional agent identifier to use for this turn.

    Yields:
        AssistantResponse: Events from the LLM.
    """
    session = _get_session(session_id)

    # Write any attachments to the virtual computer and augment the message
    # with file paths so the agent can access them via tools.
    user_content = message
    if data:
        user_content = _augment_message_with_attachments(message, data)

    if options is None:
        options = LLMOptions()
    if not options.model:
        msg = "No model specified. The UI must send a model in the request options."
        raise ValueError(msg)
    try:
        # Bridge published events via a local queue so we can stream results to the caller.
        queue: asyncio.Queue[AssistantResponse | None] = asyncio.Queue()

        async def _queue_handler(evt: AssistantResponse) -> None:
            try:
                await queue.put(evt)
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Failed to enqueue AssistantResponse in message handler")

        async def _producer() -> None:
            agent_name, agent_desc, agent_prompt, agent_tools = _resolve_agent(agent)
            active_agent = Agent(
                name=agent_name,
                description=agent_desc,
                instruction=agent_prompt,
                tools=agent_tools,
                model=options.model,  # type: ignore[arg-type]  # resolved above
                think=options.think or False,
                persist_thinking=options.persist_thinking if options.persist_thinking is not None else True,
                options=options.to_options(),
                max_iterations=options.max_iterations or 0,
            )
            # Propagate options to sub-agents via context vars
            set_model_options(options)
            # Initialize sub-agent history collector for skill extraction
            init_sub_agent_collector()

            # Lazily create the context manager with the model's context limit.
            if session.context_manager is None:
                num_ctx = active_agent.options.get("num_ctx", 0) if active_agent.options else 0
                session.context_manager = ContextManager(
                    history=session.history,
                    context_limit=num_ctx,
                    agent_name=active_agent.name,
                    strategies=[SummarizeStrategy()],
                )
            try:
                async with turn_scope(handler=_queue_handler, session_id=session_id):
                    with agent_span(active_agent.name):
                        session.history.append({"role": "user", "content": user_content})
                        _refresh_system_message(session.history, agent_prompt)
                        await session.context_manager.apply_strategies()
                        hooks = default_hooks(
                            active_agent,
                            max_iterations=active_agent.max_iterations,
                            ctx_manager=session.context_manager,
                        )

                        # Turn recording and skill tracking hooks
                        summary_cfg = None
                        try:
                            from config import load_config as _load_cfg
                            summary_cfg = _load_cfg().summary
                        except Exception:
                            pass
                        recorder = TurnRecorderHook(
                            user_message=user_content,
                            agent_name=active_agent.name,
                            model=active_agent.model,
                            conversation_id=session_id or "default",
                            summary_model=summary_cfg.model if summary_cfg else None,
                        )
                        skill_tracker = SkillTrackingHook()
                        hooks.append(recorder)
                        hooks.append(skill_tracker)

                        try:
                            async for _, _ in run_tool_call_loop(
                                history=session.history,
                                agent=active_agent,
                                hooks=hooks,
                            ):
                                pass
                        finally:
                            # Persist turn record and track skill outcome
                            record = recorder.finalize()
                            if skill_tracker.applied_skill:
                                record.metadata.skill_applied = skill_tracker.applied_skill

                            # Save full-fidelity conversation history + sub-agent histories
                            conv_id = session_id or "default"
                            save_conversation_history(conv_id, session.history.messages)
                            sub_histories = get_sub_agent_histories()
                            if sub_histories:
                                save_sub_agent_histories(conv_id, sub_histories)
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
