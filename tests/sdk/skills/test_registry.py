"""Tests for the skill registry."""

import pytest

from sdk.skills._registry import Skill, _SKILL_REGISTRY, get_skill, list_skills, register_skill


def _make_tool(name: str):
    async def tool() -> str:
        return name
    tool.__name__ = name
    return tool


@pytest.fixture(autouse=True)
def _clean_registry():
    """Snapshot and restore the registry around each test."""
    saved = dict(_SKILL_REGISTRY)
    yield
    _SKILL_REGISTRY.clear()
    _SKILL_REGISTRY.update(saved)


@pytest.mark.unit
class TestSkillRegistry:
    """Tests for register_skill, get_skill, and list_skills."""

    def test_register_and_get(self):
        """Registered skills are retrievable by name."""
        skill = Skill(
            name="test_skill",
            description="A test skill",
            prompt="Do the thing.",
            tools=[_make_tool("tool_a")],
        )
        register_skill(skill)
        assert get_skill("test_skill") is skill

    def test_get_missing(self):
        """get_skill returns None for unregistered names."""
        assert get_skill("nonexistent_skill_xyz") is None

    def test_list_skills(self):
        """list_skills returns (name, description) pairs."""
        skill = Skill(
            name="listed",
            description="A listed skill",
            prompt="prompt",
            tools=[],
        )
        register_skill(skill)
        pairs = list_skills()
        assert ("listed", "A listed skill") in pairs

    def test_overwrite_existing(self):
        """Registering a skill with the same name overwrites the old one."""
        skill_v1 = Skill(name="dup", description="v1", prompt="v1", tools=[])
        skill_v2 = Skill(name="dup", description="v2", prompt="v2", tools=[])
        register_skill(skill_v1)
        register_skill(skill_v2)
        assert get_skill("dup") is skill_v2
