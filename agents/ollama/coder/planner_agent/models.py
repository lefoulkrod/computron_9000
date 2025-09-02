"""Planner models: PlannerPlan, PlanStep, and schema helpers.

Defines the output structure for the planner agent, including a top-level
tooling selection and an ordered list of ``PlanStep`` items.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from agents.ollama.sdk.schema_tools import model_to_schema


class CommandSpec(BaseModel):
    """Specification for a short-lived shell command.

    Attributes:
        run: The shell command to execute.
        timeout_sec: Maximum allowed runtime in seconds.
    """

    run: str
    timeout_sec: int


logger = logging.getLogger(__name__)


class PlanStep(BaseModel):
    """Represents a single step in a development plan.

    Attributes:
        id: Unique identifier for this step.
        title: Human-readable title describing the step.
        step_kind: Type of step (e.g., "command" or "file").
        file_path: Optional target file path for file operations.
        command: Optional command specification to execute.
        implementation_details: Detailed list of implementation requirements.
        depends_on: Optional list of other step IDs required before this step.
    """

    id: str
    title: str
    step_kind: str
    file_path: str | None = None
    command: CommandSpec | None = None
    implementation_details: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)


class ToolingSelection(BaseModel):
    """Selected technology stack and tooling for the project.

    Attributes:
        language: Programming language to implement the project
            (e.g., "python", "javascript", "go").
        package_manager: Package/dependency manager appropriate for the chosen
            language (e.g., "uv", "npm", "go").
        test_framework: Unit test framework to use
            (e.g., "pytest", "vitest", "go test").
    """

    language: str
    package_manager: str
    test_framework: str


class PlannerPlan(BaseModel):
    """Planner output containing top-level tooling and an ordered plan.

    Attributes:
        tooling: The selected language, package manager, and unit test framework.
        steps: Ordered list of implementation steps comprising the plan.
    """

    tooling: ToolingSelection
    steps: list[PlanStep] = Field(default_factory=list)


def generate_plan_step_schema_summary() -> str:
    """Generate a simplified example JSON schema for PlanStep.

    Returns:
        JSON schema summary string.
    """
    return model_to_schema(PlanStep)


def generate_planner_plan_schema_summary(*, include_docs: bool = True) -> str:
    """Generate a simplified example JSON schema for PlannerPlan.

    Args:
        include_docs: Whether to include Google-style field docs as // comments.

    Returns:
        JSON schema summary string.
    """
    return model_to_schema(PlannerPlan, include_docs=include_docs)


__all__ = [
    "CommandSpec",
    "PlanStep",
    "PlannerPlan",
    "ToolingSelection",
    "generate_plan_step_schema_summary",
    "generate_planner_plan_schema_summary",
]
