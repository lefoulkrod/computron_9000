"""Pydantic models for conversation persistence."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolCallRecord(BaseModel):
    """A single tool invocation within a conversation turn."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_summary: str = ""
    duration_ms: int | None = None
    success: bool = True


class TurnRecord(BaseModel):
    """A single turn (user, assistant, or tool) in a conversation."""

    role: str
    content: str | None = None
    thinking: str | None = None
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    agent_name: str | None = None
    depth: int = 0
    timestamp: str = ""


class ConversationMetadata(BaseModel):
    """Summary metadata for a completed conversation."""

    task_summary: str = ""
    task_category: str = ""
    outcome: str = "unknown"  # "success" | "failure" | "partial" | "unknown"
    total_tool_calls: int = 0
    total_tokens: int = 0
    agent_chain: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    skill_applied: str | None = None
    analyzed: bool = False


class ConversationRecord(BaseModel):
    """Full record of a completed conversation."""

    id: str
    session_id: str = "default"
    started_at: str = ""
    ended_at: str = ""
    model: str = ""
    agent: str = ""
    user_message: str = ""
    turns: list[TurnRecord] = Field(default_factory=list)
    metadata: ConversationMetadata = Field(default_factory=ConversationMetadata)


class ConversationIndexEntry(BaseModel):
    """Lightweight index entry for fast filtering without loading full transcripts."""

    id: str
    user_message: str = ""
    task_category: str = ""
    outcome: str = "unknown"
    started_at: str = ""
    skill_applied: str | None = None
    analyzed: bool = False
