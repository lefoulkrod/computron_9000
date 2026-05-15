"""Tests for AgentState — base tools + dynamic skill attachment."""

import pytest

from sdk.skills._registry import Skill, _SKILL_REGISTRY, register_skill
from sdk.skills.agent_state import AgentState


def _make_tool(name: str):
    """Create a dummy tool function with a given __name__."""
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


def _make_skill(name: str, tool_names: list[str], prompt: str = "p") -> Skill:
    skill = Skill(
        name=name,
        description=f"desc_{name}",
        prompt=prompt,
        tools=[_make_tool(n) for n in tool_names],
    )
    register_skill(skill)
    return skill


@pytest.mark.unit
class TestAgentState:
    """Tests for AgentState add, dedup, find, and prompt building."""

    def test_init_copies_tools(self):
        """AgentState makes a copy of the input list."""
        original = [_make_tool("a")]
        ls = AgentState(original)
        assert len(ls.tools) == 1
        original.append(_make_tool("b"))
        assert len(ls.tools) == 1

    def test_add_adds_tools(self):
        """Adding a skill adds its tools."""
        sk = _make_skill("sk", ["b", "c"])
        ls = AgentState([_make_tool("a")])
        ls.add(sk)
        assert len(ls.tools) == 3
        assert ls.find("b") is not None
        assert ls.find("c") is not None

    def test_add_deduplicates(self):
        """Tools with the same __name__ are not added twice."""
        sk = _make_skill("sk", ["a", "b"])
        ls = AgentState([_make_tool("a")])
        ls.add(sk)
        assert len(ls.tools) == 2  # a (base) + b (skill), not a again

    def test_add_tracks_skill_name(self):
        """loaded_skill_names reflects which skills have been added."""
        browser = _make_skill("browser", ["open_url"])
        coder = _make_skill("coder", ["read_file"])
        ls = AgentState([])
        assert ls.loaded_skill_names == frozenset()
        ls.add(browser)
        assert ls.loaded_skill_names == frozenset({"browser"})
        ls.add(coder)
        assert ls.loaded_skill_names == frozenset({"browser", "coder"})

    def test_add_idempotent(self):
        """Adding the same skill twice is a no-op."""
        sk = _make_skill("sk", ["t"])
        ls = AgentState([])
        ls.add(sk)
        ls.add(sk)
        assert len(ls.tools) == 1
        assert ls.loaded_skill_names == frozenset({"sk"})

    def test_find_existing(self):
        """find() returns the tool with matching __name__."""
        tool_a = _make_tool("a")
        ls = AgentState([tool_a])
        assert ls.find("a") is tool_a

    def test_find_missing(self):
        """find() returns None for unknown tool names."""
        ls = AgentState([_make_tool("a")])
        assert ls.find("nonexistent") is None

    def test_loaded_skill_names_is_frozen(self):
        """loaded_skill_names returns a frozenset (immutable snapshot)."""
        sk = _make_skill("x", [])
        ls = AgentState([])
        ls.add(sk)
        names = ls.loaded_skill_names
        assert isinstance(names, frozenset)

    def test_build_skill_prompt_empty(self):
        """build_skill_prompt returns empty string with no skills loaded."""
        ls = AgentState([_make_tool("a")])
        assert ls.build_skill_prompt() == ""

    def test_build_skill_prompt(self):
        """build_skill_prompt includes loaded skill prompts."""
        browser = _make_skill("browser", ["open_url"], prompt="Browse the web.")
        coder = _make_skill("coder", ["read_file"], prompt="Edit files.")
        ls = AgentState([])
        ls.add(browser)
        ls.add(coder)
        prompt = ls.build_skill_prompt()
        assert "── Loaded Skills ──" in prompt
        assert "### browser" in prompt
        assert "Browse the web." in prompt
        assert "### coder" in prompt
        assert "Edit files." in prompt
