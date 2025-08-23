"""Verifier models."""

from pydantic import BaseModel, Field


class CommandOutcome(BaseModel):
    """Outcome for a single verification command."""

    command: str
    exit_code: int
    ok: bool
    stdout_preview: str | None = None
    stderr_preview: str | None = None


class VerificationReport(BaseModel):
    """Verification summary for a step."""

    success: bool
    passed: int
    failed: int
    outcomes: list[CommandOutcome] = Field(default_factory=list)
    tests_passed: bool | None = None
    mypy_ok: bool | None = None
    ruff_ok: bool | None = None


class VerifierDecision(BaseModel):
    """Decision gating advancement of a step."""

    accepted: bool
    reasons: list[str] = Field(default_factory=list)
    fixes: list[str] = Field(default_factory=list)
