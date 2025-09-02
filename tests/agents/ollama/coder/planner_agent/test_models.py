import json

import pytest

from agents.ollama.coder.planner_agent.models import (
    CommandSpec,
    PlannerPlan,
    PlanStep,
    ToolingSelection,
    generate_planner_plan_schema_summary,
)


@pytest.mark.unit
def test_planner_plan_validation_happy_path() -> None:
    """Validate minimal PlannerPlan with one step.

    Ensures schema changes (tooling + steps) parse correctly.
    """
    payload = {
        "tooling": {
            "language": "python",
            "package_manager": "uv",
            "test_framework": "pytest",
        },
        "steps": [
            {
                "id": "1",
                "title": "Init project",
                "step_kind": "command",
                "command": {"run": "uv venv && uv sync", "timeout_sec": 120},
                "implementation_details": ["create venv", "sync deps"],
                "depends_on": [],
            }
        ],
    }
    obj = PlannerPlan.model_validate(payload)
    assert isinstance(obj.tooling, ToolingSelection)
    assert obj.tooling.language == "python"
    assert len(obj.steps) == 1
    assert isinstance(obj.steps[0], PlanStep)


@pytest.mark.unit
def test_planner_plan_schema_summary_contains_tooling() -> None:
    schema_text = generate_planner_plan_schema_summary()
    # Should include top-level keys tooling and steps
    assert '"tooling"' in schema_text
    assert '"steps"' in schema_text


@pytest.mark.unit
def test_planner_plan_round_trip_json() -> None:
    obj = PlannerPlan(
        tooling=ToolingSelection(language="go", package_manager="go", test_framework="go test"),
        steps=[
            PlanStep(
                id="a",
                title="init module",
                step_kind="command",
                command=CommandSpec(run="go mod init example.com/app", timeout_sec=30),
            )
        ],
    )
    text = obj.model_dump_json()
    parsed = PlannerPlan.model_validate_json(text)
    assert parsed.tooling.language == "go"
    assert parsed.steps[0].id == "a"
