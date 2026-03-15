"""Unit tests for SkillTrackingHook."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from sdk.hooks._skill_tracking import SkillTrackingHook
from skills._models import SkillDefinition, SkillStep
from skills._registry import add_skill, get_skill


@pytest.fixture(autouse=True)
def _skills_dir(tmp_path: Path) -> Path:
    """Patch the registry path to a temp directory."""
    registry_path = tmp_path / "skills" / "registry.json"
    with patch(
        "skills._registry._get_registry_path",
        return_value=registry_path,
    ):
        yield tmp_path


@pytest.mark.unit
class TestSkillTrackingHook:
    """Tests for skill usage tracking."""

    def test_initial_state(self) -> None:
        """No skill applied initially."""
        hook = SkillTrackingHook()
        assert hook.applied_skill is None

    def test_detects_apply_skill(self) -> None:
        """Detects when apply_skill is called and bumps usage."""
        skill = SkillDefinition(
            id="",
            name="test_skill",
            description="test",
            steps=[SkillStep(description="s", tool="t")],
        )
        add_skill(skill)

        hook = SkillTrackingHook()
        result = hook.after_tool(
            "apply_skill",
            {"skill_name": "test_skill"},
            "plan output",
        )
        assert result == "plan output"
        assert hook.applied_skill == "test_skill"

        updated = get_skill("test_skill")
        assert updated is not None
        assert updated.usage_count == 1
        assert updated.last_used_at is not None

    def test_ignores_other_tools(self) -> None:
        """Ignores non-apply_skill tool calls."""
        hook = SkillTrackingHook()
        hook.after_tool("click", {"ref": "7"}, "Clicked")
        assert hook.applied_skill is None
