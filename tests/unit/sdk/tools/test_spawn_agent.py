"""Tests for sdk.tools._spawn_agent.

Focused on input-validation paths that don't require a running LLM —
specifically the disabled-profile refusal.
"""

import pytest

from sdk.tools._spawn_agent import spawn_agent


@pytest.fixture(autouse=True)
def _isolate_profiles(tmp_path, monkeypatch):
    """Point profiles at a temp directory for each test."""
    monkeypatch.setattr(
        "agents._agent_profiles._profiles_dir",
        lambda: tmp_path / "agent_profiles",
    )


@pytest.mark.unit
class TestSpawnAgentDisabledProfile:
    """spawn_agent refuses disabled profiles before touching any LLM."""

    async def test_disabled_profile_returns_error_string(self):
        """Disabled profile produces a clear error string, no LLM call."""
        from agents._agent_profiles import AgentProfile, save_agent_profile

        save_agent_profile(AgentProfile(
            id="off", name="Off", model="m", enabled=False,
        ))

        result = await spawn_agent(
            instructions="do something",
            agent_name="SUB",
            profile="off",
        )
        assert "disabled" in result
        assert "'off'" in result
        assert "list_agent_profiles" in result

    async def test_unknown_profile_returns_error_string(self):
        """Unknown profile ID produces a clear error string, no LLM call."""
        result = await spawn_agent(
            instructions="do something",
            agent_name="SUB",
            profile="ghost",
        )
        assert "not found" in result
        assert "'ghost'" in result
        assert "list_agent_profiles" in result
