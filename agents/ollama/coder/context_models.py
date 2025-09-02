"""Shared context models for coder workflow agents.

Defines standardized input payloads passed between the coder planner, coder,
and code review agents so each agent receives the same structured context.

Models use Pydantic for validation and include helpers to render concise JSON
schema examples for prompts.
"""

from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from agents.ollama.sdk.schema_tools import model_to_schema

if TYPE_CHECKING:  # pragma: no cover - for type hints only
    from agents.ollama.coder.planner_agent.models import PlanStep, ToolingSelection


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
        instructions: Ordered list of concrete actions to perform for this step.
            On retries, this may be the reviewer-required fixes instead of the
            original coder-planner output.
    """

    step: PlanStep
    tooling: ToolingSelection
    instructions: list[str] = Field(default_factory=list)


class CodeReviewInput(BaseModel):
    """Input to the code review agent for verifying a coder result.

    Attributes:
        step: The plan step that was implemented.
        tooling: The selected language, package manager, and test framework.
        instructions: The ordered actions used to guide coding for this attempt.
        coder_output: Plain-text summary from the coder describing changes and
            results.
    """

    step: PlanStep
    tooling: ToolingSelection
    instructions: list[str] = Field(default_factory=list)
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


# Ensure Pydantic resolves forward references to external models at import time
def _rebuild_models_for_pydantic() -> None:  # pragma: no cover - import-time helper
    try:
        models_mod = importlib.import_module("agents.ollama.coder.planner_agent.models")
        types_ns = {
            "PlanStep": models_mod.PlanStep,
            "ToolingSelection": models_mod.ToolingSelection,
        }
        for cls in (CoderPlannerInput, CoderInput, CodeReviewInput):
            cls.model_rebuild(_types_namespace=types_ns)
    except (ModuleNotFoundError, AttributeError) as exc:
        logging.getLogger(__name__).debug("Pydantic forward-ref rebuild skipped: %s", exc)


_rebuild_models_for_pydantic()


__all__ = [
    "CodeReviewInput",
    "CoderInput",
    "CoderPlannerInput",
    "generate_code_review_input_schema_summary",
    "generate_coder_input_schema_summary",
    "generate_coder_planner_input_schema_summary",
]
