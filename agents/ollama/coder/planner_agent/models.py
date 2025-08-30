"""Planner models: PlanStep and schema helpers."""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from agents.ollama.sdk.schema_tools import JSONValue, model_to_schema

logger = logging.getLogger(__name__)


class CommandSpec(BaseModel):
    """Specification for a shell command to execute in a plan step.

    Attributes:
        run: Shell command to execute (should be short-lived).
        timeout_sec: Maximum seconds to allow the command to run.
    """

    run: str
    timeout_sec: int = Field(ge=1, le=600, default=60)


class PlanStep(BaseModel):
    """Represents a single step in a development plan.

    Attributes:
        id: Unique identifier for this step.
        title: Human-readable title describing the step.
        step_kind: Type of step (command or file operation).
        file_path: Target file path for file operations.
        command: Command specification for command steps.
        implementation_details: List of implementation requirements.
        depends_on: List of step IDs that must complete before this step.
    """

    id: str
    title: str
    step_kind: Literal["command", "file"] | None = None
    file_path: str | None = None
    command: CommandSpec | None = None
    implementation_details: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)

    class Config:
        """Pydantic configuration for PlanStep."""

        extra = "forbid"


def generate_plan_step_schema_summary() -> str:
    """Generate a simplified example JSON schema for PlanStep.

    Returns:
        JSON schema summary string with example values.
    """
    overrides: dict[str, JSONValue] = {
        "id": "step-1",
        "title": "Initialize environment",
        "step_kind": "command",
        "command": {"run": "uv venv && uv sync", "timeout_sec": 60},
        "file_path": "src/app.py",
        "implementation_details": [
            "public API shape",
            "error handling",
        ],
    }
    return model_to_schema(PlanStep, overrides=overrides)


__all__ = [
    "CommandSpec",
    "PlanStep",
    "generate_plan_step_schema_summary",
]
