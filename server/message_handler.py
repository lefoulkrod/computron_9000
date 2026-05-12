"""Message handler for user prompts."""

import asyncio
import logging
from collections import OrderedDict
from collections.abc import AsyncGenerator, Sequence
from contextlib import suppress

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from agents import (
    AgentProfile,
    get_agent_profile,
)
from agents.types import Data
from conversations import load_conversation_history
from sdk.context import ConversationHistory
from sdk.events import (
    AgentEvent,
    ContentPayload,
    TurnEndPayload,
)
from sdk.turn import Conversation, TurnExecutor, is_turn_active
from tools.browser.core import release_agent_browser
from tools.virtual_computer.receive_file import receive_attachment

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


# In-memory conversation cache. LRU-bounded so a long-lived process
# doesn't hold every conversation a user has ever opened. The on-disk
# state is authoritative; an evicted entry is rehydrated from disk on
# next access.
_MAX_CACHED_CONVERSATIONS = 25
_conversations: OrderedDict[str, Conversation] = OrderedDict()

# Shared turn executor — stateless, safe to reuse across conversations.
_turn_executor = TurnExecutor()


async def _get_conversation(conversation_id: str) -> tuple[Conversation, bool]:
    """Return ``(conversation, is_new)`` for the given ID, creating it if needed.

    ``is_new`` is True only when the conversation has no in-memory entry
    AND no on-disk history — a genuine first-time use. On any cache miss
    we hydrate from disk so turns survive process restarts: the browser
    preserves a conversation id across server bounces (e.g. ``just
    restart-app``), and without hydration the next turn would build on an
    empty history and the persistence hook would overwrite the saved file.

    Cache hits move the entry to the end of the LRU; cache misses insert
    at the end and may evict the least-recently-used entry whose turn is
    not currently active.
    """
    if not conversation_id:
        msg = "conversation_id is required"
        raise ValueError(msg)
    if conversation_id in _conversations:
        _conversations.move_to_end(conversation_id)
        return _conversations[conversation_id], False
    persisted = load_conversation_history(conversation_id)
    is_new = persisted is None
    if is_new:
        logger.info("Creating new conversation %s", conversation_id)
    _conversations[conversation_id] = Conversation(
        id=conversation_id,
        history=ConversationHistory(persisted, instance_id=conversation_id),
    )
    await _evict_lru_conversation(exclude=conversation_id)
    return _conversations[conversation_id], is_new


async def _evict_lru_conversation(exclude: str | None = None) -> None:
    """Drop the oldest non-active entries until we are at or below the cap.

    Conversations whose turn is currently in flight are skipped — popping
    them from the dict would leave the running turn writing to a referent
    nobody else can find, and a subsequent chat for the same id would
    rehydrate from disk, producing two parallel writers.

    ``exclude`` skips the conversation that triggered this eviction. The
    caller has not yet entered ``turn_scope`` for it, so ``is_turn_active``
    cannot recognize it as protected — without this guard the just-inserted
    entry would be evicted by its own insert in the rare case where every
    other cached entry is mid-turn.
    """
    while len(_conversations) > _MAX_CACHED_CONVERSATIONS:
        for cid in _conversations:
            if cid == exclude:
                continue
            if not is_turn_active(cid):
                _conversations.pop(cid)
                await release_agent_browser(f"conv:{cid}")
                logger.info(
                    "Evicted LRU conversation %s from in-memory cache", cid,
                )
                break
        else:
            # Every cached conversation is mid-turn (or is the just-inserted
            # caller) — accept temporary overflow rather than evict an
            # active one. The next insert will retry.
            return


async def resume_conversation(conversation_id: str) -> list[dict] | None:
    """Load a conversation's full-fidelity history and install it.

    Returns the raw messages for the UI to display, or None if not found.
    """
    messages = load_conversation_history(conversation_id)
    if messages is None:
        return None

    conversation = Conversation(
        id=conversation_id,
        history=ConversationHistory(messages, instance_id=conversation_id),
    )
    _conversations[conversation_id] = conversation
    _conversations.move_to_end(conversation_id)
    await _evict_lru_conversation(exclude=conversation_id)
    return messages


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
    conversation, is_new_conversation = await _get_conversation(conversation_id)

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

    try:
        async for event in _turn_executor.execute(
            conversation=conversation,
            profile=profile,
            user_content=user_content,
            is_new_conversation=is_new_conversation,
        ):
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
