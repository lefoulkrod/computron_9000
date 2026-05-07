"""Tests for agents._agent_builder."""

import pytest

from agents import AgentProfile, build_agent


def _make_profile(**overrides) -> AgentProfile:
    defaults = {
        "id": "test",
        "name": "Test",
        "model": "test-model:7b",
        "system_prompt": "You are a test agent.",
    }
    defaults.update(overrides)
    return AgentProfile(**defaults)


def _noop() -> None:
    """Stub callable for tool lists."""


@pytest.mark.unit
class TestBuildAgent:
    """Agent construction from profile."""

    def test_basic_conversion(self):
        """Profile fields flow through to the Agent."""
        p = _make_profile(temperature=0.5, top_k=40, think=True, num_ctx=16000)
        agent = build_agent(p, tools=[_noop])
        assert agent.name == "TEST"
        assert agent.model == "test-model:7b"
        assert agent.think is True
        assert agent.instruction == "You are a test agent."
        assert agent.options == {"temperature": 0.5, "top_k": 40, "num_ctx": 16000}
        assert agent.tools == [_noop]

    def test_none_fields_omitted_from_options(self):
        """Unset profile fields don't appear in the options dict."""
        p = _make_profile()
        agent = build_agent(p, tools=[])
        assert agent.options == {}
        assert agent.max_iterations == 0
        assert agent.think is False

    def test_missing_model_raises(self):
        """Profile with no model raises RuntimeError."""
        p = _make_profile(id="child", model="")
        with pytest.raises(RuntimeError, match="no model configured"):
            build_agent(p, tools=[])

    def test_name_override(self):
        """Explicit name takes precedence over profile name."""
        p = _make_profile()
        agent = build_agent(p, tools=[], name="CUSTOM")
        assert agent.name == "CUSTOM"
