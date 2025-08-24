"""Verifier models."""

from pydantic import BaseModel, Field

__all__ = [
    "CommandOutcome",
    "VerificationReport",
    "VerifierDecision",
]


class CommandOutcome(BaseModel):
    """Result of executing a single verification command.

    Attributes:
        command: The shell command that was executed.
        exit_code: Exit code returned by the command.
        ok: Whether the command succeeded (exit code 0).
        stdout_preview: Preview of command standard output, if any.
        stderr_preview: Preview of command standard error, if any.
    """

    command: str
    exit_code: int
    ok: bool
    stdout_preview: str | None = None
    stderr_preview: str | None = None


class VerificationReport(BaseModel):
    """Summary report of step verification results.

    Attributes:
        success: Whether all verification checks passed.
        passed: Number of verification checks that passed.
        failed: Number of verification checks that failed.
        outcomes: List of individual command outcomes.
        tests_passed: Whether automated tests passed, None if not run.
        mypy_ok: Whether mypy type checking passed, None if not run.
        ruff_ok: Whether ruff linting passed, None if not run.
    """

    success: bool
    passed: int
    failed: int
    outcomes: list[CommandOutcome] = Field(default_factory=list)
    tests_passed: bool | None = None
    mypy_ok: bool | None = None
    ruff_ok: bool | None = None


class VerifierDecision(BaseModel):
    """Decision on whether to accept or reject a development step.

    Attributes:
        accepted: Whether the step was accepted for advancement.
        reasons: List of reasons supporting the decision.
        fixes: List of suggested fixes if step was rejected.
    """

    accepted: bool
    reasons: list[str] = Field(default_factory=list)
    fixes: list[str] = Field(default_factory=list)
