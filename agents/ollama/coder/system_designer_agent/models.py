"""Pydantic models for system designer outputs."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from agents.ollama.sdk.schema_tools import model_to_schema

logger = logging.getLogger(__name__)


class Artifact(BaseModel):
    """A concrete deliverable with implementation guidance.

    Attributes:
        name: Identifier for the artifact.
        path: Relative path to the artifact file.
        user_stories: User stories this artifact fulfills.
        detailed_requirements: Concrete requirements for implementation.
        acceptance_criteria: Checklist for validating the artifact.
        depends_on: Optional names of artifacts this depends on.
    """

    name: str
    path: str
    user_stories: list[str] = Field(default_factory=list)
    detailed_requirements: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)


class SystemDesign(BaseModel):
    """Top-level system design produced by the designer agent.

    Attributes:
        summary: One-paragraph overview.
        success_criteria: Measurable acceptance criteria.
        assumptions: Assumptions made by the designer.
        language: Primary implementation language.
        dependency_manager: Dependency manager for the project.
        packages: Additional packages to include.
        artifacts: Concrete artifacts to implement.
        test_framework: Primary test framework/tool.
    """

    summary: str
    success_criteria: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    language: str | None = None
    dependency_manager: str | None = None
    packages: list[str] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    test_framework: str | None = None


def generate_json_schema() -> dict[str, Any]:  # pragma: no cover
    """Return full JSON Schema for SystemDesign."""
    return SystemDesign.model_json_schema()


def generate_schema_summary() -> str:
    """Return simplified placeholder JSON for prompts and docs."""
    return model_to_schema(SystemDesign)


__all__ = [
    "Artifact",
    "SystemDesign",
    "generate_json_schema",
    "generate_schema_summary",
]
