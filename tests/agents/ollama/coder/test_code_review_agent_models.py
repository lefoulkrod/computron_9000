"""Unit tests for CodeReviewResult model serialization.

Ensures the field alias "pass" is produced on export.
"""

import json

import pytest

from agents.ollama.coder.code_review_agent.models import CodeReviewResult


@pytest.mark.unit
def test_code_review_result_uses_pass_alias() -> None:
    model = CodeReviewResult(passed=True, fixes=["none"])
    data = json.loads(model.model_dump_json(by_alias=True))
    assert "pass" in data and data["pass"] is True
    assert "passed" not in data
    assert data["fixes"] == ["none"]
