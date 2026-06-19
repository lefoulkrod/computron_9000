"""Tests for sdk.turn._executor.TurnExecutor — pre-wired turn driver."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from agents.types import Agent
from sdk import Conversation, TurnExecutor
from sdk.context import ConversationHistory
from sdk.skills import AgentState
from sdk.skills._registry import Skill

_MOD = "sdk.turn._executor"


def _make_agent(**overrides: Any) -> Agent:
    defaults = {
        "name": "test-agent",
        "description": "test",
        "instruction": "BASE INSTRUCTION",
        "provider": "ollama",
        "model": "test-model",
        "options": {},
        "tools": [],
        "think": False,
        "context_window": 0,
        "compaction_threshold": 0.75,
        "max_iterations": 0,
    }
    defaults.update(overrides)
    return Agent(**defaults)


def _make_conversation(
    conv_id: str = "c1", *, agent_state: AgentState | None = None,
) -> Conversation:
    return Conversation(
        id=conv_id,
        history=ConversationHistory(instance_id=conv_id),
        agent_state=agent_state if agent_state is not None else AgentState([]),
    )


def _fake_skill(name: str) -> Skill:
    return Skill(name=name, description=f"{name} skill", prompt=f"{name}-prompt", tools=[])


async def _drain(executor_call):
    """Iterate the async-generator to completion and collect events."""
    return [evt async for evt in executor_call]


# ---------------------------------------------------------------------------
# agent_state contract — must be populated before execute()
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_missing_agent_state_raises():
    """The executor refuses to run when the caller forgot to populate it."""
    conv = Conversation(
        id="c1",
        history=ConversationHistory(instance_id="c1"),
    )
    agent = _make_agent()

    with pytest.raises(ValueError, match="agent_state"):
        await _drain(TurnExecutor().execute(
            conversation=conv, agent=agent, user_content="hi",
        ))


# ---------------------------------------------------------------------------
# History writes — user message append + system prompt placement
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_user_message_appended_to_history():
    conv = _make_conversation()
    agent = _make_agent()

    with patch(f"{_MOD}.run_turn", new_callable=AsyncMock):
        await _drain(TurnExecutor().execute(
            conversation=conv, agent=agent, user_content="hello world",
        ))

    user_msgs = [m for m in conv.history.messages if m["role"] == "user"]
    assert len(user_msgs) == 1
    assert user_msgs[0]["content"] == "hello world"


@pytest.mark.unit
async def test_system_message_is_agent_instruction_when_no_skills_loaded():
    conv = _make_conversation()
    agent = _make_agent(instruction="MY INSTRUCTION")

    with patch(f"{_MOD}.run_turn", new_callable=AsyncMock):
        await _drain(TurnExecutor().execute(
            conversation=conv, agent=agent, user_content="hi",
        ))

    system = conv.history.messages[0]
    assert system["role"] == "system"
    assert system["content"] == "MY INSTRUCTION"


@pytest.mark.unit
async def test_system_message_includes_skill_prompt_when_skills_loaded():
    """When agent_state has skills, their prompts append to the agent's instruction."""
    state = AgentState([])
    state.add(_fake_skill("alpha"))
    state.add(_fake_skill("beta"))
    conv = _make_conversation(agent_state=state)
    agent = _make_agent(instruction="BASE")

    with patch(f"{_MOD}.run_turn", new_callable=AsyncMock):
        await _drain(TurnExecutor().execute(
            conversation=conv, agent=agent, user_content="hi",
        ))

    system = conv.history.messages[0]["content"]
    assert system.startswith("BASE")
    assert "alpha-prompt" in system
    assert "beta-prompt" in system


@pytest.mark.unit
async def test_executor_does_not_load_skills_or_call_persistence():
    """Verify the executor stays out of the persistence/skill-loading business
    (those moved to callers in the refactor)."""
    state = AgentState([])
    conv = _make_conversation(agent_state=state)
    agent = _make_agent()

    with (
        patch(f"{_MOD}.run_turn", new_callable=AsyncMock),
        # If the executor reached for the registry we'd see it here.
        patch("sdk.skills._registry.get_skill") as get_skill_mock,
    ):
        await _drain(TurnExecutor().execute(
            conversation=conv, agent=agent, user_content="hi",
        ))

    assert get_skill_mock.call_count == 0
    assert state.loaded_skill_names == frozenset()
