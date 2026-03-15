"""Unit tests for skill tool functions (lookup_skills, apply_skill)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from skills._models import SkillDefinition, SkillStep
from skills._registry import add_skill
from tools.skills._tools import apply_skill, lookup_skills


@pytest.fixture(autouse=True)
def _skills_dir(tmp_path: Path) -> Path:
    """Patch the registry path to a temp directory."""
    registry_path = tmp_path / "skills" / "registry.json"
    with patch(
        "skills._registry._get_registry_path",
        return_value=registry_path,
    ):
        yield tmp_path


def _add_sample_skill() -> SkillDefinition:
    """Add a sample skill to the registry and return it."""
    skill = SkillDefinition(
        id="",
        name="scrape_recipes",
        description="Scrape recipe websites for ingredients and instructions",
        agent_scope="COMPUTRON_9000",
        trigger_patterns=["find recipes", "scrape recipes", "get recipes"],
        steps=[
            SkillStep(
                description="Search for recipes via browser",
                tool="browser_agent_tool",
                notes="Use {dish} as the search query",
            ),
            SkillStep(
                description="Save results to file",
                tool="computer_agent_tool",
            ),
        ],
        usage_count=12,
    )
    return add_skill(skill)


@pytest.mark.unit
class TestLookupSkills:
    """Tests for the lookup_skills tool function."""

    @pytest.mark.asyncio
    async def test_no_results(self) -> None:
        """Empty registry returns no matches."""
        result = await lookup_skills("anything")
        assert result["status"] == "ok"
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_finds_matching_skill(self) -> None:
        """Finds skills matching the query."""
        _add_sample_skill()
        result = await lookup_skills("recipes")
        assert result["status"] == "ok"
        assert result["count"] == 1
        assert "scrape_recipes" in result["skills"]


@pytest.mark.unit
class TestApplySkill:
    """Tests for the apply_skill tool function."""

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        """Applying missing skill returns not_found."""
        result = await apply_skill("nonexistent")
        assert result["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_apply_returns_plan(self) -> None:
        """Apply a skill returns execution plan with steps."""
        _add_sample_skill()
        result = await apply_skill("scrape_recipes")
        assert result["status"] == "ok"
        assert result["skill_name"] == "scrape_recipes"
        plan = result["plan"]
        assert "browser_agent_tool" in plan
        assert "used 12 times" in plan
