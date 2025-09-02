"""Unit tests for shared coder context models.

Validates that the standardized context payloads can be instantiated and
round-tripped through JSON without loss.
"""

from __future__ import annotations

import json

import pytest

from agents.ollama.coder.context_models import (
    CoderInput,
    CoderPlannerInput,
    CodeReviewInput,
)
from agents.ollama.coder.planner_agent.models import CommandSpec, PlanStep, ToolingSelection


@pytest.mark.unit
def test_coder_planner_input_round_trip() -> None:
    """CoderPlannerInput should serialize/deserialize consistently."""
    step = PlanStep(
        id="1",
        title="Init project",
        step_kind="command",
        command=CommandSpec(run="uv sync", timeout_sec=120),
        implementation_details=["Initialize environment"],
    )
    tooling = ToolingSelection(language="python", package_manager="uv", test_framework="pytest")
    payload = CoderPlannerInput(step=step, tooling=tooling)
    raw = payload.model_dump_json()
    restored = CoderPlannerInput.model_validate_json(raw)
    assert restored.step.id == step.id
    assert restored.tooling.language == "python"


@pytest.mark.unit
def test_coder_input_round_trip() -> None:
    """CoderInput should serialize/deserialize consistently."""
    step = PlanStep(id="2", title="Create file", step_kind="file", file_path="README.md")
    tooling = ToolingSelection(language="python", package_manager="uv", test_framework="pytest")
    payload = CoderInput(
        step=step,
        tooling=tooling,
        planner_instructions=["Create README.md with project info"],
        fixes=None,
    )
    raw = payload.model_dump_json()
    restored = CoderInput.model_validate_json(raw)
    assert restored.step.title == "Create file"
    assert restored.planner_instructions == ["Create README.md with project info"]


@pytest.mark.unit
def test_code_review_input_round_trip() -> None:
    """CodeReviewInput should serialize/deserialize consistently."""
    step = PlanStep(id="3", title="Run tests", step_kind="command")
    tooling = ToolingSelection(language="python", package_manager="uv", test_framework="pytest")
    payload = CodeReviewInput(
        step=step,
        tooling=tooling,
        planner_instructions=["Run uv run pytest -q"],
        coder_output="Ran tests; all passed",
    )
    raw = payload.model_dump_json()
    data = json.loads(raw)
    assert data["tooling"]["test_framework"] == "pytest"
    restored = CodeReviewInput.model_validate_json(raw)
    assert restored.coder_output.startswith("Ran tests")
