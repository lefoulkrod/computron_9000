"""Pydantic models for the skills system."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SkillParameter(BaseModel):
    """A single parameter for a skill definition."""

    name: str
    description: str
    type: str = "string"  # "string" | "url" | "file_path" | "number"
    required: bool = True
    example: str = ""


class SkillStep(BaseModel):
    """A single step in a skill workflow."""

    description: str
    tool: str
    argument_template: dict[str, Any] = Field(default_factory=dict)
    expected_outcome: str = ""
    notes: str = ""


class SkillDefinition(BaseModel):
    """Full definition of a reusable skill (workflow recipe)."""

    id: str
    name: str
    description: str
    agent_scope: str = "ANY"  # "COMPUTRON_9000" | "BROWSER_AGENT" | "COMPUTER_AGENT" | "ANY"
    trigger_patterns: list[str] = Field(default_factory=list)
    category: str = ""
    parameters: list[SkillParameter] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    steps: list[SkillStep] = Field(default_factory=list)
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    source_conversations: list[str] = Field(default_factory=list)
    # Confidence and tracking
    confidence: float = 0.5
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    last_used_at: str | None = None
    active: bool = True
