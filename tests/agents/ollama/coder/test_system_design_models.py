"""Unit tests for SystemDesign artifacts structure and validation.

Verifies that:
- schema summary includes artifacts with expected fields
- valid SystemDesign with artifacts passes validation
- Artifact forbids extra fields
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from agents.ollama.coder.system_designer_agent.models import (
    Artifact,
    SystemDesign,
    generate_schema_summary,
)


@pytest.mark.unit
def test_schema_summary_includes_artifacts_fields() -> None:
    """Schema summary should expose artifacts with the expected keys."""
    summary_json = generate_schema_summary()
    data = json.loads(summary_json)
    assert "artifacts" in data
    assert isinstance(data["artifacts"], list)
    # Expect a single example object within the list
    example = data["artifacts"][0]
    for key in (
        "name",
        "path",
        "user_stories",
        "detailed_requirements",
        "acceptance_criteria",
        "depends_on",
    ):
        assert key in example


@pytest.mark.unit
def test_system_design_validates_with_artifacts() -> None:
    """A minimal, valid SystemDesign with an artifact should validate."""
    sd = SystemDesign(
        summary="Example system",
        success_criteria=["Runs", "Has tests"],
        assumptions=["Single user"],
        language="python",
        dependency_manager="uv",
        test_framework="pytest",
        packages=["fastapi"],
        artifacts=[
            Artifact(
                name="AppModule",
                path="src/app.py",
                user_stories=[
                    "As a developer I want an app entrypoint so that I can run the service",
                ],
                detailed_requirements=[
                    "Provide a FastAPI app with a health endpoint at /health",
                    "Return JSON {\"status\": \"ok\"}",
                ],
                acceptance_criteria=[
                    "uv run pytest passes",
                    "GET /health returns 200 and status ok",
                ],
            )
        ],
    )
    dumped = sd.model_dump()
    assert dumped["language"] == "python"
    assert len(dumped["artifacts"]) == 1
    art = dumped["artifacts"][0]
    assert art["path"] == "src/app.py"


@pytest.mark.unit
def test_artifact_forbids_extra_fields() -> None:
    """Artifacts should forbid additional unexpected fields."""
    with pytest.raises(ValidationError):
        Artifact(
            name="X",
            path="src/x.py",
            user_stories=[],
            detailed_requirements=[],
            acceptance_criteria=[],
            extra_field="nope",  # type: ignore[arg-type]
        )
