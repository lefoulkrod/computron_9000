"""Tests for the skill registry."""

import pytest

from sdk.skills._registry import (
    Skill,
    _SKILL_REGISTRY,
    _strip_grounding_tools,
    get_skill,
    list_skills,
    register_skill,
)


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


@pytest.mark.unit
def test_strip_grounding_tools_removes_browser_visual_action():
    """The browser skill loses browser_visual_action when grounding is off."""
    from tools.browser.vision import browser_visual_action
    from tools.browser import open_url

    skill = Skill(
        name="browser",
        description="test",
        prompt="p",
        tools=[open_url, browser_visual_action],
    )
    stripped = _strip_grounding_tools(skill)
    assert browser_visual_action not in stripped.tools
    assert open_url in stripped.tools


@pytest.mark.unit
def test_strip_grounding_tools_removes_perform_visual_action():
    """The desktop skill loses perform_visual_action when grounding is off."""
    from tools.desktop._tools import perform_visual_action, mouse_click

    skill = Skill(
        name="desktop",
        description="test",
        prompt="p",
        tools=[mouse_click, perform_visual_action],
    )
    stripped = _strip_grounding_tools(skill)
    assert perform_visual_action not in stripped.tools
    assert mouse_click in stripped.tools


@pytest.mark.unit
def test_strip_grounding_tools_returns_same_skill_when_no_match():
    """No grounding tools → returns the input untouched (identity preserved)."""
    skill = Skill(
        name="coder",
        description="test",
        prompt="p",
        tools=[_make_tool("write_file")],
    )
    assert _strip_grounding_tools(skill) is skill
