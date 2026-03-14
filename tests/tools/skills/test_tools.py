"""Unit tests for skill tool functions (lookup_skills, apply_skill)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tools.skills._models import SkillDefinition, SkillParameter, SkillStep
from tools.skills._registry import add_skill
from tools.skills._tools import apply_skill, lookup_skills


@pytest.fixture(autouse=True)
def _skills_dir(tmp_path: Path) -> Path:
    """Patch the registry path to a temp directory."""
    registry_path = tmp_path / "skills" / "registry.json"
    with patch(
        "tools.skills._registry._get_registry_path",
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
        category="web_scraping",
        trigger_patterns=["find recipes", "scrape recipes", "get recipes"],
        parameters=[
            SkillParameter(
                name="dish",
                description="The dish to search for",
                type="string",
                required=True,
                example="pasta",
            ),
        ],
        steps=[
            SkillStep(
                description="Search for recipes via browser",
                tool="browser_agent_tool",
                argument_template={"instructions": "Search for {dish} recipes"},
                expected_outcome="Recipe data returned",
            ),
            SkillStep(
                description="Save results to file",
                tool="computer_agent_tool",
                argument_template={"instructions": "Write recipes to /home/computron/recipes.md"},
                expected_outcome="File written",
            ),
        ],
        confidence=0.85,
        usage_count=12,
        success_count=10,
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

    @pytest.mark.asyncio
    async def test_search_by_category(self) -> None:
        """Finds skills by category keyword."""
        _add_sample_skill()
        result = await lookup_skills("web_scraping")
        assert result["count"] == 1


@pytest.mark.unit
class TestApplySkill:
    """Tests for the apply_skill tool function."""

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        """Applying missing skill returns not_found."""
        result = await apply_skill("nonexistent")
        assert result["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_apply_with_params(self) -> None:
        """Apply a skill with parameters filled in."""
        _add_sample_skill()
        result = await apply_skill("scrape_recipes", '{"dish": "pasta"}')
        assert result["status"] == "ok"
        assert result["skill_name"] == "scrape_recipes"
        plan = result["plan"]
        assert "pasta" in plan
        assert "browser_agent_tool" in plan
        assert "confidence: 85%" in plan

    @pytest.mark.asyncio
    async def test_missing_required_param(self) -> None:
        """Missing required parameter returns error."""
        _add_sample_skill()
        result = await apply_skill("scrape_recipes", "{}")
        assert result["status"] == "error"
        assert "dish" in result["message"]

    @pytest.mark.asyncio
    async def test_invalid_json(self) -> None:
        """Invalid JSON returns error."""
        _add_sample_skill()
        result = await apply_skill("scrape_recipes", "not json")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_inactive_skill(self) -> None:
        """Applying an inactive skill returns inactive status."""
        _add_sample_skill()
        from tools.skills._registry import toggle_skill
        toggle_skill("scrape_recipes", active=False)

        result = await apply_skill("scrape_recipes", '{"dish": "pasta"}')
        assert result["status"] == "inactive"

    @pytest.mark.asyncio
    async def test_default_empty_params(self) -> None:
        """Apply with default empty params still works if no required params."""
        skill = SkillDefinition(
            id="",
            name="simple_skill",
            description="No params needed",
            steps=[
                SkillStep(description="Do thing", tool="run_bash_cmd", argument_template={"cmd": "echo hi"}),
            ],
        )
        add_skill(skill)
        result = await apply_skill("simple_skill")
        assert result["status"] == "ok"
