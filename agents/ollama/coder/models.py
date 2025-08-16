"""Strict data models for the coder workflow orchestration.

Defines PlanStep per the planner schema and StepResult for step-level reporting.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class FileSpec(BaseModel):
    """File to create or modify in a plan step.

    Args:
        path: Relative file path to create/edit.
        purpose: Short description of the file's purpose.
    """

    path: str
    purpose: str


class CommandSpec(BaseModel):
    """Command to run for a plan step.

    Args:
        run: Shell command to run (single, short-lived).
        timeout_sec: Max seconds to allow the command to run.
    """

    run: str
    timeout_sec: int = Field(ge=1, le=600, default=60)


class TestSpec(BaseModel):
    """Test file to create for a plan step.

    Args:
        path: Relative path of the test file.
        description: What the test validates.
    """

    path: str
    description: str


class PlanStep(BaseModel):
    """Strict planner step schema.

    Fields mirror the proposal's strict planner schema.
    """

    id: str
    title: str
    instructions: str
    files: list[FileSpec] = Field(default_factory=list)
    commands: list[CommandSpec] = Field(default_factory=list)
    tests: list[TestSpec] = Field(default_factory=list)
    acceptance: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    retries: int | None = Field(default=None, ge=0, le=5)
    when: str | None = None

    class Config:
        """Pydantic configuration for PlanStep."""

        extra = "forbid"


class CommandOutcome(BaseModel):
    """Outcome for a single verification command.

    Args:
        command: The command that was executed.
        exit_code: Process exit code.
        ok: True if exit_code == 0.
        stdout_preview: Optional truncated stdout summary.
        stderr_preview: Optional truncated stderr summary.
    """

    command: str
    exit_code: int
    ok: bool
    stdout_preview: str | None = None
    stderr_preview: str | None = None


class VerificationReport(BaseModel):
    """Language-agnostic verification summary for a step.

    Args:
        success: True iff all verification commands succeeded.
        passed: Count of successful commands.
        failed: Count of failed commands.
        outcomes: Per-command outcomes.
        tests_passed: Optional, for Python-style test suites.
        mypy_ok: Optional, for Python static typing.
        ruff_ok: Optional, for Python linting.
    """

    success: bool
    passed: int
    failed: int
    outcomes: list[CommandOutcome] = Field(default_factory=list)
    tests_passed: bool | None = None
    mypy_ok: bool | None = None
    ruff_ok: bool | None = None


class ReviewerDecision(BaseModel):
    """Reviewer outcome as strict JSON."""

    decision: Literal["accepted", "rejected"]
    reasons: list[str] = Field(default_factory=list)
    must_fixes: list[str] = Field(default_factory=list)
    nice_to_haves: list[str] = Field(default_factory=list)


class StepResult(BaseModel):
    """Step execution result surface for UI and logging."""

    step_id: str
    title: str
    started_at: float
    finished_at: float
    completed: bool
    artifacts: list[str] = Field(default_factory=list)
    verification: VerificationReport | None = None
    logs: list[str] = Field(default_factory=list)
    error: str | None = None
