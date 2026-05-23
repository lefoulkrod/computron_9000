"""Tests for sdk.turn._executor.TurnExecutor — injection points + persistence."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.types import Agent
from sdk import Conversation, TurnExecutor
from sdk.context import ConversationHistory
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


def _make_conversation(conv_id: str = "c1") -> Conversation:
    return Conversation(
        id=conv_id,
        history=ConversationHistory(instance_id=conv_id),
    )


class _FakePersistence:
    """Implements the TurnPersistence protocol with recording stubs."""

    def __init__(self, persisted_skills: list[str] | None = None) -> None:
        self._persisted_skills = persisted_skills or []
        self.load_skills_calls: list[str] = []
        self.save_skills_calls: list[tuple[str, list[str]]] = []
        self.save_events_calls: list[tuple[str, list[Any]]] = []
        self.on_new_calls: list[tuple[str, str]] = []

    def load_skills(self, conversation_id: str):
        self.load_skills_calls.append(conversation_id)
        return list(self._persisted_skills)

    def save_skills(self, conversation_id: str, skills) -> None:
        self.save_skills_calls.append((conversation_id, sorted(skills)))

    def save_events(self, conversation_id: str, events) -> None:
        self.save_events_calls.append((conversation_id, list(events)))

    async def on_new_conversation(self, conversation_id: str, first_message: str) -> None:
        self.on_new_calls.append((conversation_id, first_message))


async def _drain(executor_call):
    """Iterate the async-generator to completion and collect events."""
    return [evt async for evt in executor_call]


# ---------------------------------------------------------------------------
# build_system_prompt
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_build_system_prompt_result_is_used_as_base():
    conv = _make_conversation()
    agent = _make_agent(instruction="DEFAULT")

    with patch(f"{_MOD}.run_turn", new_callable=AsyncMock):
        await _drain(TurnExecutor().execute(
            conversation=conv,
            agent=agent,
            user_content="hi",
            build_system_prompt=lambda: "FRESH PROMPT",
        ))

    # The system message ends up at index 0 of history.
    system = conv.history.messages[0]
    assert system["role"] == "system"
    assert system["content"] == "FRESH PROMPT"


@pytest.mark.unit
async def test_no_builder_falls_back_to_agent_instruction():
    conv = _make_conversation()
    agent = _make_agent(instruction="DEFAULT")

    with patch(f"{_MOD}.run_turn", new_callable=AsyncMock):
        await _drain(TurnExecutor().execute(
            conversation=conv,
            agent=agent,
            user_content="hi",
        ))

    assert conv.history.messages[0]["content"] == "DEFAULT"


@pytest.mark.unit
async def test_builder_is_called_fresh_each_turn():
    """The closure is re-evaluated per turn so live state (memory) lands fresh."""
    conv = _make_conversation()
    agent = _make_agent()

    call_count = 0
    def _builder() -> str:
        nonlocal call_count
        call_count += 1
        return f"prompt-{call_count}"

    with patch(f"{_MOD}.run_turn", new_callable=AsyncMock):
        await _drain(TurnExecutor().execute(
            conversation=conv, agent=agent, user_content="t1",
            build_system_prompt=_builder,
        ))
        await _drain(TurnExecutor().execute(
            conversation=conv, agent=agent, user_content="t2",
            build_system_prompt=_builder,
        ))

    assert call_count == 2
    assert conv.history.messages[0]["content"] == "prompt-2"


# ---------------------------------------------------------------------------
# user_content append + system prompt placement
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_user_message_appended_to_history():
    conv = _make_conversation()
    agent = _make_agent()

    with patch(f"{_MOD}.run_turn", new_callable=AsyncMock):
        await _drain(TurnExecutor().execute(
            conversation=conv, agent=agent, user_content="hello world",
        ))

    roles = [m["role"] for m in conv.history.messages]
    assert "user" in roles
    user_msg = next(m for m in conv.history.messages if m["role"] == "user")
    assert user_msg["content"] == "hello world"


# ---------------------------------------------------------------------------
# Skill preloading + persistence restore
# ---------------------------------------------------------------------------


def _fake_skill(name: str) -> Skill:
    return Skill(name=name, description=f"{name} skill", prompt=f"{name}-prompt", tools=[])


@pytest.mark.unit
async def test_preloaded_skills_added_via_registry():
    conv = _make_conversation()
    agent = _make_agent()

    skills_lookup = {"foo": _fake_skill("foo"), "bar": _fake_skill("bar")}

    with (
        patch(f"{_MOD}.run_turn", new_callable=AsyncMock),
        patch(f"{_MOD}.get_skill", side_effect=lambda n: skills_lookup.get(n)),
    ):
        await _drain(TurnExecutor().execute(
            conversation=conv, agent=agent, user_content="hi",
            preloaded_skills=["foo", "bar"],
        ))

    # Skill names land in the system prompt via build_skill_prompt.
    system = conv.history.messages[0]["content"]
    assert "foo-prompt" in system
    assert "bar-prompt" in system


@pytest.mark.unit
async def test_preloaded_skill_not_in_registry_is_logged_and_skipped(caplog):
    conv = _make_conversation()
    agent = _make_agent()

    with (
        patch(f"{_MOD}.run_turn", new_callable=AsyncMock),
        patch(f"{_MOD}.get_skill", return_value=None),
        caplog.at_level("WARNING"),
    ):
        await _drain(TurnExecutor().execute(
            conversation=conv, agent=agent, user_content="hi",
            preloaded_skills=["ghost"],
        ))

    # Logged a warning; no crash.
    assert any("ghost" in rec.getMessage() for rec in caplog.records)


@pytest.mark.unit
async def test_persistence_load_skills_restores_them():
    conv = _make_conversation()
    agent = _make_agent()
    persistence = _FakePersistence(persisted_skills=["restored_a", "restored_b"])
    skills = {n: _fake_skill(n) for n in ("restored_a", "restored_b")}

    with (
        patch(f"{_MOD}.run_turn", new_callable=AsyncMock),
        patch(f"{_MOD}.get_skill", side_effect=lambda n: skills.get(n)),
    ):
        await _drain(TurnExecutor().execute(
            conversation=conv, agent=agent, user_content="hi",
            persistence=persistence,
        ))

    assert persistence.load_skills_calls == [conv.id]
    system = conv.history.messages[0]["content"]
    assert "restored_a-prompt" in system
    assert "restored_b-prompt" in system


# ---------------------------------------------------------------------------
# Persistence write paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_persistence_save_skills_called_with_loaded_names():
    conv = _make_conversation()
    agent = _make_agent()
    persistence = _FakePersistence()
    skill = _fake_skill("alpha")

    with (
        patch(f"{_MOD}.run_turn", new_callable=AsyncMock),
        patch(f"{_MOD}.get_skill", return_value=skill),
    ):
        await _drain(TurnExecutor().execute(
            conversation=conv, agent=agent, user_content="hi",
            preloaded_skills=["alpha"],
            persistence=persistence,
        ))

    assert persistence.save_skills_calls == [(conv.id, ["alpha"])]


@pytest.mark.unit
async def test_persistence_save_skills_skipped_when_no_skills_loaded():
    conv = _make_conversation()
    agent = _make_agent()
    persistence = _FakePersistence()

    with patch(f"{_MOD}.run_turn", new_callable=AsyncMock):
        await _drain(TurnExecutor().execute(
            conversation=conv, agent=agent, user_content="hi",
            persistence=persistence,
        ))

    assert persistence.save_skills_calls == []


@pytest.mark.unit
async def test_on_new_conversation_fires_only_when_flagged():
    conv = _make_conversation()
    agent = _make_agent()
    persistence = _FakePersistence()

    with patch(f"{_MOD}.run_turn", new_callable=AsyncMock):
        await _drain(TurnExecutor().execute(
            conversation=conv, agent=agent, user_content="first-turn",
            is_new_conversation=True,
            persistence=persistence,
        ))

    # on_new_conversation runs as a background task — give it a turn.
    import asyncio
    await asyncio.sleep(0)
    assert persistence.on_new_calls == [(conv.id, "first-turn")]


@pytest.mark.unit
async def test_on_new_conversation_skipped_on_continuation():
    conv = _make_conversation()
    agent = _make_agent()
    persistence = _FakePersistence()

    with patch(f"{_MOD}.run_turn", new_callable=AsyncMock):
        await _drain(TurnExecutor().execute(
            conversation=conv, agent=agent, user_content="t",
            is_new_conversation=False,
            persistence=persistence,
        ))

    import asyncio
    await asyncio.sleep(0)
    assert persistence.on_new_calls == []


# ---------------------------------------------------------------------------
# persistence=None — every persistence call must be skipped
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_no_persistence_is_safe():
    conv = _make_conversation()
    agent = _make_agent()
    skill = _fake_skill("alpha")

    with (
        patch(f"{_MOD}.run_turn", new_callable=AsyncMock),
        patch(f"{_MOD}.get_skill", return_value=skill),
    ):
        # Nothing should raise, even with preloaded skills and is_new=True.
        await _drain(TurnExecutor().execute(
            conversation=conv, agent=agent, user_content="hi",
            is_new_conversation=True,
            preloaded_skills=["alpha"],
            persistence=None,
        ))
