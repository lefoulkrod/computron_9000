"""Tests that agent_span properly scopes the AgentState ContextVar."""

import pytest

from sdk.events._context import agent_span
from sdk.skills.agent_state import AgentState, _active_agent_state


def _make_tool(name: str):
    async def tool() -> str:
        return name
    tool.__name__ = name
    return tool


@pytest.mark.unit
class TestAgentSpanAgentStateIsolation:
    """Verify agent_span resets and restores the AgentState ContextVar."""

    @pytest.mark.asyncio
    async def test_agent_span_creates_fresh_agent_state(self):
        """Inside an agent_span, a fresh AgentState is created."""
        parent = AgentState([_make_tool("parent_tool")])
        token = _active_agent_state.set(parent)
        try:
            async with agent_span("child"):
                child = _active_agent_state.get()
                assert child is not None
                assert child is not parent
                assert child.tools == []
        finally:
            _active_agent_state.reset(token)

    @pytest.mark.asyncio
    async def test_agent_span_restores_parent(self):
        """After exiting agent_span, the parent's AgentState is restored."""
        parent = AgentState([_make_tool("parent_tool")])
        token = _active_agent_state.set(parent)
        try:
            async with agent_span("child"):
                child = _active_agent_state.get()
                assert child is not parent

            assert _active_agent_state.get() is parent
        finally:
            _active_agent_state.reset(token)

    @pytest.mark.asyncio
    async def test_nested_spans(self):
        """Nested agent_spans each get their own isolated scope."""
        root = AgentState([_make_tool("root")])
        token = _active_agent_state.set(root)
        try:
            async with agent_span("level1", agent_state=AgentState([_make_tool("l1")])):
                level1 = _active_agent_state.get()
                assert level1 is not root
                assert len(level1.tools) == 1

                async with agent_span("level2", agent_state=AgentState([_make_tool("l2")])):
                    level2 = _active_agent_state.get()
                    assert level2 is not level1
                    assert len(level2.tools) == 1

                assert _active_agent_state.get() is level1

            assert _active_agent_state.get() is root
        finally:
            _active_agent_state.reset(token)

    @pytest.mark.asyncio
    async def test_default_creates_empty_agent_state(self):
        """Without any setup, agent_span creates an empty AgentState."""
        async with agent_span("clean"):
            ls = _active_agent_state.get()
            assert ls is not None
            assert ls.tools == []
        assert _active_agent_state.get() is None
