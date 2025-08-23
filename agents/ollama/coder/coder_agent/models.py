"""Coder agent result models."""

from pydantic import BaseModel, Field

from agents.ollama.coder.verifier_agent.models import VerificationReport


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
