"""Unit tests for skill registry CRUD operations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tools.skills._models import SkillDefinition, SkillParameter, SkillStep
from tools.skills._registry import (
    add_skill,
    delete_skill,
    get_skill,
    list_skills,
    record_skill_usage,
    search_skills,
    toggle_skill,
)


@pytest.fixture(autouse=True)
def _skills_dir(tmp_path: Path) -> Path:
    """Patch the registry path to a temp directory."""
    registry_path = tmp_path / "skills" / "registry.json"
    with patch(
        "tools.skills._registry._get_registry_path",
        return_value=registry_path,
    ):
        yield tmp_path


def _make_skill(
    name: str = "test_skill",
    description: str = "A test skill",
    agent_scope: str = "ANY",
    category: str = "other",
) -> SkillDefinition:
    return SkillDefinition(
        id="",
        name=name,
        description=description,
        agent_scope=agent_scope,
        category=category,
        trigger_patterns=[f"do {name}"],
        steps=[
            SkillStep(
                description="Step 1",
                tool="run_bash_cmd",
                argument_template={"cmd": "echo hello"},
            ),
        ],
    )


@pytest.mark.unit
class TestSkillRegistry:
    """Tests for skill registry CRUD."""

    def test_add_and_get(self) -> None:
        """Add a skill and retrieve it."""
        skill = _make_skill()
        added = add_skill(skill)
        assert added.id != ""
        assert added.created_at != ""

        found = get_skill("test_skill")
        assert found is not None
        assert found.name == "test_skill"

    def test_add_duplicate_raises(self) -> None:
        """Adding a duplicate without overwrite raises."""
        add_skill(_make_skill())
        with pytest.raises(ValueError, match="already exists"):
            add_skill(_make_skill())

    def test_add_overwrite(self) -> None:
        """Overwriting preserves ID and usage stats."""
        original = add_skill(_make_skill())
        record_skill_usage("test_skill", success=True)

        updated = add_skill(
            _make_skill(description="Updated"),
            overwrite=True,
        )
        assert updated.id == original.id
        assert updated.description == "Updated"
        assert updated.usage_count == 1  # Preserved

    def test_get_nonexistent(self) -> None:
        """Getting a missing skill returns None."""
        assert get_skill("nope") is None

    def test_search(self) -> None:
        """Search by keywords."""
        add_skill(_make_skill("scrape_prices", "Scrape product prices", category="web_scraping"))
        add_skill(_make_skill("generate_report", "Generate a report"))

        results = search_skills("scrape prices")
        assert len(results) == 1
        assert results[0].name == "scrape_prices"

        results = search_skills("web_scraping")
        assert len(results) == 1

    def test_search_agent_scope_filter(self) -> None:
        """Search respects agent_scope filter."""
        add_skill(_make_skill("browser_skill", agent_scope="BROWSER_AGENT"))
        add_skill(_make_skill("any_skill", agent_scope="ANY"))

        results = search_skills("skill", agent_scope="BROWSER_AGENT")
        assert len(results) == 2  # BROWSER_AGENT + ANY
        names = {r.name for r in results}
        assert "browser_skill" in names
        assert "any_skill" in names

        results = search_skills("skill", agent_scope="COMPUTER_AGENT")
        assert len(results) == 1  # Only ANY
        assert results[0].name == "any_skill"

    def test_list_skills(self) -> None:
        """List all active skills."""
        add_skill(_make_skill("s1"))
        add_skill(_make_skill("s2"))

        skills = list_skills()
        assert len(skills) == 2

    def test_list_includes_inactive(self) -> None:
        """List with active_only=False includes inactive."""
        add_skill(_make_skill("active"))
        s = add_skill(_make_skill("inactive"))
        toggle_skill("inactive", active=False)

        active = list_skills(active_only=True)
        assert len(active) == 1

        all_skills = list_skills(active_only=False)
        assert len(all_skills) == 2

    def test_delete(self) -> None:
        """Delete a skill."""
        add_skill(_make_skill())
        assert delete_skill("test_skill") is True
        assert get_skill("test_skill") is None

    def test_delete_nonexistent(self) -> None:
        """Deleting a missing skill returns False."""
        assert delete_skill("nope") is False

    def test_toggle_skill(self) -> None:
        """Toggle active state."""
        add_skill(_make_skill())
        assert toggle_skill("test_skill", active=False) is True

        skill = get_skill("test_skill")
        assert skill is not None
        assert skill.active is False

        toggle_skill("test_skill", active=True)
        skill = get_skill("test_skill")
        assert skill is not None
        assert skill.active is True

    def test_toggle_nonexistent(self) -> None:
        """Toggling missing skill returns False."""
        assert toggle_skill("nope", active=True) is False


@pytest.mark.unit
class TestSkillUsageTracking:
    """Tests for usage counting and confidence scoring."""

    def test_record_success(self) -> None:
        """Record a successful usage."""
        add_skill(_make_skill())
        record_skill_usage("test_skill", success=True)

        skill = get_skill("test_skill")
        assert skill is not None
        assert skill.usage_count == 1
        assert skill.success_count == 1
        assert skill.confidence == 1.0
        assert skill.last_used_at is not None

    def test_record_failure(self) -> None:
        """Record a failed usage."""
        add_skill(_make_skill())
        record_skill_usage("test_skill", success=False)

        skill = get_skill("test_skill")
        assert skill is not None
        assert skill.failure_count == 1
        assert skill.confidence == 0.0

    def test_confidence_calculation(self) -> None:
        """Confidence is success_count / usage_count."""
        add_skill(_make_skill())
        record_skill_usage("test_skill", success=True)
        record_skill_usage("test_skill", success=True)
        record_skill_usage("test_skill", success=False)

        skill = get_skill("test_skill")
        assert skill is not None
        assert skill.usage_count == 3
        assert skill.confidence == pytest.approx(2 / 3)

    def test_auto_deactivate_low_confidence(self) -> None:
        """Skills with low confidence after 5+ uses are auto-deactivated."""
        add_skill(_make_skill())
        # 5 failures, 0 successes → confidence = 0.0
        for _ in range(5):
            record_skill_usage("test_skill", success=False)

        skill = get_skill("test_skill")
        assert skill is not None
        assert skill.active is False
