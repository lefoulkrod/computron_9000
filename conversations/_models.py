"""Pydantic models for conversation persistence."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SummaryRecord(BaseModel):
    """Record of a single context summarization event.

    Saved to ``{conv_dir}/summaries/{id}.json`` on every compaction.
    Stores everything needed to reconstruct the original conversation
    and audit compaction quality.
    """

    id: str
    """Unique record identifier (UUID)."""

    created_at: str = ""
    """ISO-8601 timestamp. Used to order records chronologically for
    reconstruction — the earliest record contains the true original
    user message."""

    model: str = ""
    """LLM model that produced the summary (e.g. ``kimi-k2.5:cloud``)."""

    input_messages: list[dict[str, Any]] = Field(default_factory=list)
    """Full-fidelity messages that were compacted. May include a synthetic
    summary message from an earlier compaction (starts with
    ``[Conversation summary``). Skip those during reconstruction — the
    originals are in an earlier record."""

    input_char_count: int = 0
    """Total character count across all ``input_messages``."""

    prior_summary: str | None = None
    """Summary text from the previous compaction, if one existed in the
    compactable window. Also present as a message in ``input_messages``."""

    summary_text: str = ""
    """The summary this compaction produced. Inserted into the conversation
    as an assistant message prefixed with ``[Conversation summary ...]``."""

    summary_char_count: int = 0
    """Character length of ``summary_text``."""

    messages_compacted: int = 0
    """Number of messages replaced by the summary."""

    fill_ratio: float = 0.0
    """Context window fill ratio that triggered this compaction."""

    conversation_id: str = ""
    """ID of the conversation this record belongs to."""

    agent_name: str = ""
    """Name of the agent whose history was compacted (root or sub-agent)."""

    options: dict[str, Any] = Field(default_factory=dict)
    """Model options used for the summarizer call (num_ctx, temperature, etc.)."""

    elapsed_seconds: float | None = None
    """Wall-clock time for the summarizer LLM call(s)."""

    source_history: str = ""
    """Instance ID of the ``ConversationHistory`` that was compacted."""

    user_message_pre_compaction: str | None = None
    """Pinned user message content *before* this compaction mutates it.
    On the first compaction this is the user's original message; on
    subsequent compactions it is the previous intent history. The true
    original is in the earliest summary record (by ``created_at``)."""

    user_message_post_compaction: str | None = None
    """Pinned user message content *after* this compaction. When the
    conversation has multiple user messages, intent extraction replaces
    the pinned message with a concise history of how the user's requests
    evolved. ``None`` if no intent extraction ran (single-user-message
    conversations)."""


class ClearedItem(BaseModel):
    """A single item that was cleared from conversation history."""

    message_index: int
    role: str  # "tool" or "assistant"
    tool_name: str = ""
    cleared_type: str = ""  # "tool_result" or "tool_arg"
    arg_key: str = ""
    original_content: str = ""
    original_chars: int = 0


class ClearingRecord(BaseModel):
    """Record of a single tool clearing event for quality evaluation."""

    id: str
    created_at: str = ""
    conversation_id: str = ""
    agent_name: str = ""
    fill_ratio: float = 0.0
    total_chars_freed: int = 0
    results_cleared: int = 0
    args_cleared: int = 0
    threshold: float = 0.0
    keep_recent_groups: int = 0
    cleared_items: list[ClearedItem] = Field(default_factory=list)
    source_history: str = ""


class ConversationSummary(BaseModel):
    """Summary of a conversation for listing in the UI."""

    conversation_id: str
    first_message: str = ""
    title: str = ""  # Auto-generated title (max 60 chars)
    started_at: str = ""
    turn_count: int = 0
