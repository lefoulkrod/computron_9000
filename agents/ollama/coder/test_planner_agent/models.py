"""Test planner models."""

from pydantic import BaseModel, Field


class QATestFilePlan(BaseModel):
    """Specification for a test file the QA agent wants created."""

    path: str
    purpose: str


class QATestCommandPlan(BaseModel):
    """Command the QA agent recommends running to validate the step."""

    run: str
    timeout_sec: int = Field(ge=1, le=600, default=120)


class QATestPlan(BaseModel):
    """Structured QA plan focusing on unit tests for a coder step."""

    summary: str
    test_files: list[QATestFilePlan] = Field(default_factory=list)
    commands: list[QATestCommandPlan] = Field(default_factory=list)
    rationale: str | None = None
