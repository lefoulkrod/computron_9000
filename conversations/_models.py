"""Pydantic models for conversation and turn persistence."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolCallRecord(BaseModel):
    """A single tool invocation within a turn."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_summary: str = ""
    duration_ms: int | None = None
    success: bool = True


class MessageRecord(BaseModel):
    """A single message (user, assistant, or tool) in a turn."""

    role: str
    content: str | None = None
    thinking: str | None = None
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    agent_name: str | None = None
    depth: int = 0
    timestamp: str = ""


class TurnMetadata(BaseModel):
    """Summary metadata for a completed turn."""

    task_summary: str = ""
    task_category: str = ""
    outcome: str = "unknown"  # "success" | "failure" | "partial" | "unknown"
    total_tool_calls: int = 0
    total_tokens: int = 0
    agent_chain: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    skill_applied: str | None = None
    analyzed: bool = False


class TurnRecord(BaseModel):
    """Full record of a completed turn (one user request -> agent response)."""

    id: str
    conversation_id: str = "default"
    started_at: str = ""
    ended_at: str = ""
    model: str = ""
    agent: str = ""
    user_message: str = ""
    messages: list[MessageRecord] = Field(default_factory=list)
    metadata: TurnMetadata = Field(default_factory=TurnMetadata)


class TurnIndexEntry(BaseModel):
    """Lightweight index entry for fast filtering without loading full transcripts."""

    id: str
    conversation_id: str = "default"
    user_message: str = ""
    task_category: str = ""
    outcome: str = "unknown"
    started_at: str = ""
    skill_applied: str | None = None
    analyzed: bool = False


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


class ConversationSummary(BaseModel):
    """Summary of a full conversation (all turns)."""

    conversation_id: str
    turn_count: int = 0
    first_message: str = ""
    outcomes: list[str] = Field(default_factory=list)
    started_at: str = ""
    ended_at: str = ""
    total_tool_calls: int = 0
    analyzed: bool = False
