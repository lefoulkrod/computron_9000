"""Shared context models for coder workflow agents.

Defines standardized input payloads passed between the coder planner, coder,
and code review agents so each agent receives the same structured context.

Models use Pydantic for validation and include helpers to render concise JSON
schema examples for prompts.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.ollama.coder.planner_agent.models import PlanStep, ToolingSelection
from agents.ollama.sdk.schema_tools import model_to_schema


class CoderPlannerInput(BaseModel):
    """Input to the coder-planner agent.

    Attributes:
        step: The current plan step to expand into coder sub-steps.
        tooling: The selected language, package manager, and test framework
            from the top-level plan.
    """

    step: PlanStep
    tooling: ToolingSelection


class CoderInput(BaseModel):
    """Input to the coder agent for implementing a plan step.

    Attributes:
        step: The current plan step being implemented.
        tooling: The selected language, package manager, and test framework.
        planner_instructions: Ordered list of sub-steps produced by the
            coder-planner for this step.
        fixes: Optional required changes from code review when retrying.
    """

    step: PlanStep
    tooling: ToolingSelection
    planner_instructions: list[str] = Field(default_factory=list)
    fixes: list[str] | None = None


class CodeReviewInput(BaseModel):
    """Input to the code review agent for verifying a coder result.

    Attributes:
        step: The plan step that was implemented.
        tooling: The selected language, package manager, and test framework.
        planner_instructions: The coder-planner output used to guide coding.
        coder_output: Plain-text summary from the coder describing changes and
            results.
    """

    step: PlanStep
    tooling: ToolingSelection
    planner_instructions: list[str] = Field(default_factory=list)
    coder_output: str


def generate_coder_planner_input_schema_summary(*, include_docs: bool = True) -> str:
    """Return example JSON schema for ``CoderPlannerInput`` for prompts.

    Args:
        include_docs: Whether to include Google-style field docs as // comments.

    Returns:
        JSON schema summary string.
    """
    return model_to_schema(CoderPlannerInput, include_docs=include_docs)


def generate_coder_input_schema_summary(*, include_docs: bool = True) -> str:
    """Return example JSON schema for ``CoderInput`` for prompts.

    Args:
        include_docs: Whether to include Google-style field docs as // comments.

    Returns:
        JSON schema summary string.
    """
    return model_to_schema(CoderInput, include_docs=include_docs)


def generate_code_review_input_schema_summary(*, include_docs: bool = True) -> str:
    """Return example JSON schema for ``CodeReviewInput`` for prompts.

    Args:
        include_docs: Whether to include Google-style field docs as // comments.

    Returns:
        JSON schema summary string.
    """
    return model_to_schema(CodeReviewInput, include_docs=include_docs)


__all__ = [
    "CodeReviewInput",
    "CoderInput",
    "CoderPlannerInput",
    "generate_code_review_input_schema_summary",
    "generate_coder_input_schema_summary",
    "generate_coder_planner_input_schema_summary",
]
