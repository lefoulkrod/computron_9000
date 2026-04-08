"""Message handler for user prompts."""

import logging
from collections.abc import AsyncGenerator, Sequence

from sdk.context import ConversationHistory
from sdk.events import AgentEvent, ContentPayload, TurnEndPayload
from sdk.turn import Conversation, TurnExecutor
from agents.types import Data, LLMOptions
from tools.virtual_computer.receive_file import receive_attachment

from agents import AVAILABLE_AGENTS
from conversations import load_conversation_history

logger = logging.getLogger(__name__)

_DEFAULT_CONVERSATION_ID = "default"

# Module-level turn executor shared across all SSE conversations.
_turn_executor = TurnExecutor()

# Conversation store keyed by conversation ID.
_conversations: dict[str, Conversation] = {}


def _get_conversation(conversation_id: str | None = None) -> Conversation:
    """Return the conversation for the given ID, creating one if needed."""
    cid = conversation_id or _DEFAULT_CONVERSATION_ID
    if cid not in _conversations:
        _conversations[cid] = Conversation(
            id=cid,
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

    conversation = Conversation(
        id=conversation_id,
        history=ConversationHistory(messages, instance_id=conversation_id),
    )
    _conversations[conversation_id] = conversation
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
    return (
        f"{message}\n\n"
        f"[Attached files written to virtual computer]\n"
        f"{files_block}"
    )


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
    cid = conversation_id or _DEFAULT_CONVERSATION_ID
    is_new_conversation = cid not in _conversations
    conversation = _get_conversation(conversation_id)

    user_content = message
    if data:
        user_content = _augment_message_with_attachments(message, data)

    if not options.model:
        msg = "No model specified. The UI must send a model in the request options."
        raise ValueError(msg)

    try:
        async for event in _turn_executor.execute(
            conversation=conversation,
            user_content=user_content,
            agent_id=agent,
            options=options,
            is_new_conversation=is_new_conversation,
        ):
            yield event
    except Exception:
        logger.exception("Error handling user message")
        yield AgentEvent(payload=ContentPayload(
            type="content",
            content="An error occurred while processing your message.",
        ))
        yield AgentEvent(payload=TurnEndPayload(type="turn_end"))