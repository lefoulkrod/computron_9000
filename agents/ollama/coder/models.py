"""Strict data models for the coder workflow orchestration.

Defines PlanStep per the planner schema and StepResult for step-level reporting.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from utils.pydantic_schema import JSONValue, schema_summary

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
    user_stories: list[str] = Field(default_factory=list)

    class Config:
        """Pydantic configuration for PlanStep."""

        extra = "forbid"


def generate_plan_step_schema_summary() -> str:
    """Return simplified placeholder JSON schema for PlanStep.

    Uses shared utility with overrides for key scalar examples.
    """
    overrides: dict[str, JSONValue] = {
        "id": "step-1",
        "title": "Initialize environment",
    }
    return schema_summary(PlanStep, overrides=overrides)


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


class VerifierDecision(BaseModel):
    """Gating verifier decision JSON replacing the old reviewer model.

    Args:
        accepted: True if the step can advance; False to request rework.
        reasons: Explanation supporting the decision.
        fixes: Concrete fix instructions when not accepted.
    """

    accepted: bool
    reasons: list[str] = Field(default_factory=list)
    fixes: list[str] = Field(default_factory=list)

    class Config:
        """Pydantic configuration (forbid extras)."""

        extra = "forbid"


class QATestFilePlan(BaseModel):
    """Specification for a test file the QA agent wants created.

    Args:
        path: Relative path to the test file to create (e.g. tests/module/test_feature.py).
        purpose: Brief description of what scenarios the test file covers.
    """

    path: str
    purpose: str


class QATestCommandPlan(BaseModel):
    """Command the QA agent recommends running to validate the step.

    Args:
        run: Shell command (short-lived) to execute tests or static analysis.
        timeout_sec: Upper bound runtime seconds.
    """

    run: str
    timeout_sec: int = Field(ge=1, le=600, default=120)


class QATestPlan(BaseModel):
    """Structured QA plan focusing on unit tests for a coder step.

    Returned by the QA agent. The verifier will later execute the listed commands.

    Args:
        summary: Short natural language summary of the QA approach.
        test_files: List of test files to create/update.
        commands: Verification commands (pytest, mypy, ruff, etc.).
        rationale: Optional reasoning for chosen tests/commands.
    """

    summary: str
    test_files: list[QATestFilePlan] = Field(default_factory=list)
    commands: list[QATestCommandPlan] = Field(default_factory=list)
    rationale: str | None = None

    class Config:
        """Pydantic configuration (forbid extras to keep schema strict)."""

        extra = "forbid"


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
