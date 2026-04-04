"""Tests for the load_skill meta-tool."""

import pytest

from sdk.skills._tools import load_skill
from sdk.skills._registry import Skill, _SKILL_REGISTRY, register_skill
from sdk.skills.agent_state import AgentState, _active_agent_state


def _make_tool(name: str):
    async def tool() -> str:
        return name
    tool.__name__ = name
    tool.__doc__ = f"Tool {name}."
    return tool


@pytest.fixture(autouse=True)
def _clean_registry():
    """Snapshot and restore the registry around each test."""
    saved = dict(_SKILL_REGISTRY)
    yield
    _SKILL_REGISTRY.clear()
    _SKILL_REGISTRY.update(saved)


@pytest.fixture()
def loaded_skills():
    """Create an AgentState and set it as the active one for the test."""
    ls = AgentState([_make_tool("preexisting")])
    token = _active_agent_state.set(ls)
    yield ls
    _active_agent_state.reset(token)


@pytest.mark.unit
class TestLoadSkill:
    """Tests for the load_skill tool function."""

    @pytest.mark.asyncio
    async def test_load_adds_tools(self, loaded_skills):
        """Loading a skill adds its tools to the active AgentState."""
        register_skill(Skill(
            name="test_sk",
            description="test",
            prompt="Use these tools.",
            tools=[_make_tool("new_tool")],
        ))
        result = await load_skill("test_sk")
        assert loaded_skills.find("new_tool") is not None
        assert "test_sk" in loaded_skills.loaded_skill_names
        assert "Loaded" in result

    @pytest.mark.asyncio
    async def test_load_returns_confirmation(self, loaded_skills):
        """load_skill returns a confirmation, not the prompt itself."""
        register_skill(Skill(
            name="prompted",
            description="d",
            prompt="Follow this workflow carefully.",
            tools=[],
        ))
        result = await load_skill("prompted")
        assert "Loaded" in result
        assert "system prompt" in result

    @pytest.mark.asyncio
    async def test_already_loaded(self, loaded_skills):
        """Loading the same skill twice returns a no-op message."""
        register_skill(Skill(
            name="once",
            description="d",
            prompt="p",
            tools=[_make_tool("t")],
        ))
        await load_skill("once")
        result = await load_skill("once")
        assert "already loaded" in result

    @pytest.mark.asyncio
    async def test_unknown_skill(self, loaded_skills):
        """Unknown skill name returns error with available list."""
        register_skill(Skill(
            name="known",
            description="a known skill",
            prompt="p",
            tools=[],
        ))
        result = await load_skill("bogus")
        assert "Unknown skill" in result
        assert "known" in result

    @pytest.mark.asyncio
    async def test_no_active_agent_state(self):
        """load_skill without active AgentState returns an error."""
        token = _active_agent_state.set(None)
        try:
            result = await load_skill("anything")
            assert "Error" in result
        finally:
            _active_agent_state.reset(token)
