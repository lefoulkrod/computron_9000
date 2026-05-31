"""Message handler for user prompts."""

import asyncio
import logging
from collections.abc import AsyncGenerator, Sequence

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from agents import (
    AgentProfile,
    build_agent,
    get_agent_profile,
)
from agents.types import Data
from conversations import (
    ConversationCache,
    DiskTurnPersistence,
    load_agent_events,
    load_preview_state,
)
from sdk import TurnExecutor
from sdk.events import (
    AgentEvent,
    ContentPayload,
    TurnEndPayload,
)
from sdk.skills import AgentState
from sdk.turn import is_turn_active
from tools.browser.core import release_agent_browser
from tools.memory import forget, memory_prompt_block, remember
from tools.virtual_computer.receive_file import receive_attachment
from tools.virtual_computer.run_bash_cmd import run_bash_cmd

# Background tasks held to prevent GC; cleared via done callback.
_background_tasks: set[asyncio.Task] = set()

logger = logging.getLogger(__name__)
_console = Console(stderr=True)


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
    if profile.repeat_penalty is not None:
        params.append(f"repeat_penalty={profile.repeat_penalty}")
    if profile.num_predict is not None:
        params.append(f"num_predict={profile.num_predict}")
    if profile.context_window is not None:
        params.append(f"ctx={profile.context_window}")
    if profile.compaction_threshold is not None:
        params.append(f"compact@{int(profile.compaction_threshold * 100)}%")
    if profile.think:
        params.append("think")
    if profile.reasoning_effort is not None:
        params.append(f"reasoning_effort={profile.reasoning_effort}")
    if profile.reasoning_summary is not None:
        params.append(f"reasoning_summary={profile.reasoning_summary}")
    if profile.thinking_budget is not None:
        params.append(f"thinking_budget={profile.thinking_budget}")
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


# Shared in-memory conversation cache. The on-disk store is authoritative;
# the cache exists so consecutive turns reuse the same Conversation object
# (and the PersistenceHook's in-place history mutations survive across
# turns). Eviction releases per-conversation browser contexts so evicted
# rows don't leak a Playwright instance.
_cache = ConversationCache(
    is_active=is_turn_active,
    on_evict=lambda cid: release_agent_browser(f"conv:{cid}"),
)

# Shared turn executor — stateless, safe to reuse across conversations.
_turn_executor = TurnExecutor()
_persistence = DiskTurnPersistence()


async def resume_conversation(conversation_id: str) -> dict | None:
    """Load a conversation's full-fidelity history, events, and preview state.

    Returns a dict with:
        messages: LLM messages from history.json.
        events: persisted agent events (file_output, browser_screenshot, etc.)
            from events.json. The UI uses these to reconstruct inline file
            blocks in the chat and the preview tabs on restore.
        preview_state: persisted preview-panel state (open file list,
            active tab, per-preview visibility flags).

    None if the conversation isn't found.
    """
    conversation = await _cache.resume(conversation_id)
    if conversation is None:
        return None
    return {
        "messages": list(conversation.history.messages),
        "events": load_agent_events(conversation_id),
        "preview_state": load_preview_state(conversation_id),
    }


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


async def handle_user_message(
    message: str,
    data: Sequence[Data] | None = None,
    *,
    profile_id: str | None = None,
    conversation_id: str,
) -> AsyncGenerator[AgentEvent, None]:
    """Handles a user message by sending it to the LLM and yielding events.

    Args:
        message: The user's message.
        data: Optional sequence of file attachment data.
        profile_id: Agent profile to use. Required.
        conversation_id: Conversation identifier for isolation. Required.

    Yields:
        AgentEvent: Events from the LLM.
    """
    if not conversation_id:
        msg = "conversation_id is required"
        raise ValueError(msg)
    conversation, is_new_conversation = await _cache.get(conversation_id)

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

    _log_turn_start(profile)

    if conversation.agent_state is None:
        conversation.agent_state = await AgentState.create(
            skill_names=[*profile.skills, *_persistence.load_skills(conversation.id)],
        )

    agent = build_agent(profile, tools=[run_bash_cmd, remember, forget])
    agent.instruction = memory_prompt_block() + agent.instruction

    events: list[AgentEvent] = []
    try:
        async for event in _turn_executor.execute(
            conversation=conversation,
            agent=agent,
            user_content=user_content,
            profile_name=profile.name,
        ):
            events.append(event)
            yield event
    except Exception:
        logger.exception("Error handling user message")
        yield AgentEvent(
            payload=ContentPayload(
                type="content",
                content="An error occurred while processing your message.",
            )
        )
        yield AgentEvent(payload=TurnEndPayload(type="turn_end"))
        return

    # Post-turn persistence. Errors logged, never raised — the user already
    # got their reply.
    try:
        _persistence.save_events(conversation.id, events)
    except Exception:
        logger.exception("Failed to save agent events for '%s'", conversation.id)
    if conversation.agent_state.loaded_skill_names:
        try:
            _persistence.save_skills(
                conversation.id,
                conversation.agent_state.loaded_skill_names,
            )
        except Exception:
            logger.exception("Failed to save loaded skills for '%s'", conversation.id)
    if is_new_conversation:
        task = asyncio.create_task(
            _persistence.on_new_conversation(conversation.id, user_content),
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
