"""Pydantic models for conversation persistence."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SummaryRecord(BaseModel):
    """Record of a single context summarization event for quality evaluation."""

    id: str
    created_at: str = ""
    model: str = ""
    input_messages: list[dict[str, Any]] = Field(default_factory=list)
    input_char_count: int = 0
    prior_summary: str | None = None
    summary_text: str = ""
    summary_char_count: int = 0
    messages_compacted: int = 0
    fill_ratio: float = 0.0
    conversation_id: str = ""
    agent_name: str = ""
    options: dict[str, Any] = Field(default_factory=dict)
    elapsed_seconds: float | None = None


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


class ConversationSummary(BaseModel):
    """Summary of a conversation for listing in the UI."""

    conversation_id: str
    first_message: str = ""
    started_at: str = ""
    turn_count: int = 0
