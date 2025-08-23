"""Planner models: PlanStep and schema helpers."""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from utils.pydantic_schema import JSONValue, schema_summary

logger = logging.getLogger(__name__)


class CommandSpec(BaseModel):
    """Command to run for a plan step.

    Args:
        run: Shell command to run (single, short-lived).
        timeout_sec: Max seconds to allow the command to run.
    """

    run: str
    timeout_sec: int = Field(ge=1, le=600, default=60)


class PlanStep(BaseModel):
    """Strict planner step schema.

    Fields mirror the proposal's strict planner schema.
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
    """Return simplified placeholder JSON schema for PlanStep."""
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
    return schema_summary(PlanStep, overrides=overrides)


__all__ = [
    "CommandSpec",
    "PlanStep",
    "generate_plan_step_schema_summary",
]
