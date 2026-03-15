"""Pydantic models for the skills system."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SkillStep(BaseModel):
    """A single step in a skill workflow."""

    description: str
    tool: str
    notes: str = ""


class SkillDefinition(BaseModel):
    """Full definition of a reusable skill (workflow recipe)."""

    id: str
    name: str
    description: str
    agent_scope: str = "ANY"  # "COMPUTRON_9000" | "BROWSER_AGENT" | "COMPUTER_AGENT" | "ANY"
    trigger_patterns: list[str] = Field(default_factory=list)
    steps: list[SkillStep] = Field(default_factory=list)
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    source_conversations: list[str] = Field(default_factory=list)
    usage_count: int = 0
    last_used_at: str | None = None
