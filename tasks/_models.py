"""Pydantic models for the task engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _new_id() -> str:
    """Generate a unique ID for task engine entities."""
    return uuid4().hex


def _utcnow() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


class Goal(BaseModel):
    """An immutable template that defines what to accomplish."""

    id: str = Field(default_factory=_new_id)
    description: str
    status: Literal["active", "paused"] = "active"
    cron: str | None = None
    timezone: str = "UTC"  # IANA timezone name (e.g., "America/Chicago")
    created_at: str = Field(default_factory=_utcnow)


class Task(BaseModel):
    """An immutable definition of a unit of work belonging to a goal."""

    id: str = Field(default_factory=_new_id)
    goal_id: str
    description: str
    instruction: str
    agent: str = "computron"
    agent_config: dict[str, Any] | None = None
    depends_on: list[str] = Field(default_factory=list)
    max_retries: int = 3


class Run(BaseModel):
    """A single execution of a goal."""

    id: str = Field(default_factory=_new_id)
    goal_id: str
    run_number: int = 1
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    created_at: str = Field(default_factory=_utcnow)
    started_at: str | None = None
    completed_at: str | None = None


class TaskResult(BaseModel):
    """Per-run execution state for a single task."""

    id: str = Field(default_factory=_new_id)
    run_id: str
    task_id: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    result: str | None = None
    error: str | None = None
    retry_count: int = 0
    started_at: str | None = None
    completed_at: str | None = None
    conversation_id: str | None = None
    file_outputs: list[str] = Field(default_factory=list)


__all__ = ["Goal", "Run", "Task", "TaskResult"]
