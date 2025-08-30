"""Planner models: PlanStep and schema helpers."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from agents.ollama.sdk.schema_tools import model_to_schema

logger = logging.getLogger(__name__)


class PlanStep(BaseModel):
    """Represents a single step in a development plan.

    Attributes:
        id: Unique identifier for this step.
        title: Human-readable title describing the step.
        step_kind: Type of step (command or file operation).
        file_path: An optional target file path for file operations.
        command: An optional shell command to execute.
        implementation_details: Detailed list of implementation requirements.
        depends_on: An optional list of components this step depends on.
    """

    id: str
    title: str
    step_kind: str
    file_path: str | None = None
    command: str | None = None
    implementation_details: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)

    class Config:
        """Pydantic configuration for PlanStep."""

        extra = "forbid"


def generate_plan_step_schema_summary() -> str:
    """Generate a simplified example JSON schema for PlanStep.

    Returns:
        JSON schema summary string.
    """
    return model_to_schema(PlanStep)


__all__ = [
    "PlanStep",
    "generate_plan_step_schema_summary",
]
