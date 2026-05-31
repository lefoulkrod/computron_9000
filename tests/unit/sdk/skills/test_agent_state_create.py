"""Tests for AgentState.create() — the async factory used by all callsites."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from sdk.skills._registry import Skill, _SKILL_REGISTRY, register_skill
from sdk.skills.agent_state import AgentState

_MOD = "sdk.skills.agent_state"


def _make_tool(name: str):
    async def tool() -> str:
        return name
    tool.__name__ = name
    return tool


def _make_skill(name: str, tool_names: list[str]) -> Skill:
    return Skill(
        name=name,
        description=f"desc_{name}",
        prompt=f"{name}-prompt",
        tools=[_make_tool(t) for t in tool_names],
    )


@pytest.fixture(autouse=True)
def _clean_registry():
    saved = dict(_SKILL_REGISTRY)
    yield
    _SKILL_REGISTRY.clear()
    _SKILL_REGISTRY.update(saved)


@pytest.mark.unit
async def test_create_pulls_core_tools_and_starts_empty_without_skills():
    core = [_make_tool("core_a"), _make_tool("core_b")]
    with patch(f"{_MOD}.get_core_tools", new=AsyncMock(return_value=core)):
        state = await AgentState.create()

    assert state.loaded_skill_names == frozenset()
    names = [getattr(t, "__name__", None) for t in state.tools]
    assert names == ["core_a", "core_b"]


@pytest.mark.unit
async def test_create_loads_named_skills_from_registry():
    register_skill(_make_skill("alpha", ["a_tool"]))
    register_skill(_make_skill("beta", ["b_tool"]))

    with patch(f"{_MOD}.get_core_tools", new=AsyncMock(return_value=[])):
        state = await AgentState.create(skill_names=["alpha", "beta"])

    assert state.loaded_skill_names == frozenset({"alpha", "beta"})
    names = {getattr(t, "__name__", None) for t in state.tools}
    assert names == {"a_tool", "b_tool"}


@pytest.mark.unit
async def test_create_logs_and_skips_unknown_skills(caplog):
    register_skill(_make_skill("known", ["t"]))

    with (
        patch(f"{_MOD}.get_core_tools", new=AsyncMock(return_value=[])),
        caplog.at_level("WARNING"),
    ):
        state = await AgentState.create(skill_names=["known", "ghost"])

    assert state.loaded_skill_names == frozenset({"known"})
    assert any("ghost" in rec.getMessage() for rec in caplog.records)


@pytest.mark.unit
async def test_create_deduplicates_repeated_skill_names():
    register_skill(_make_skill("alpha", ["a_tool"]))

    with patch(f"{_MOD}.get_core_tools", new=AsyncMock(return_value=[])):
        state = await AgentState.create(skill_names=["alpha", "alpha", "alpha"])

    assert state.loaded_skill_names == frozenset({"alpha"})
