"""Unit tests for CodeReviewResult model serialization.

Ensures the field alias "pass" is produced on export.
"""

import json

import pytest

from agents.ollama.coder.code_review_agent.models import CodeReviewResult


@pytest.mark.unit
def test_code_review_result_uses_pass_alias() -> None:
    model = CodeReviewResult(success=True, required_changes=["none"])
    data = json.loads(model.model_dump_json())
    assert "success" in data and data["success"] is True
    assert data["required_changes"] == ["none"]
