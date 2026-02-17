"""Coder agent result models."""

from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "StepResult",
]


class StepResult(BaseModel):
    """Represents the execution result of a development step.

    Attributes:
        step_id: Unique identifier for the step.
        title: Human-readable title describing the step.
        started_at: Unix timestamp when step execution began.
        finished_at: Unix timestamp when step execution completed.
        completed: Whether the step finished successfully.
        artifacts: List of file paths or outputs created during step execution.
        verification: Verification report if step was verified, None otherwise.
        logs: List of log messages from step execution.
        error: Error message if step failed, None otherwise.
    """

    step_id: str
    title: str
    started_at: float
    finished_at: float
    completed: bool
    artifacts: list[str] = Field(default_factory=list)
    verification: dict[str, Any] | None = None
    logs: list[str] = Field(default_factory=list)
    error: str | None = None
