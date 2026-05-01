"""Tests for tasks._executor.

Coverage gap this file addresses: the executor is the bridge between the
task scheduler and the agent runtime. It calls ``get_core_tools()``, which
is async because integrated tool gating awaits the integrations cache.
A regression that drops the ``await`` somewhere in the executor causes
``AgentState(coroutine)`` → ``TypeError: 'coroutine' object is not iterable``
at goal-run time, and goal runs fail with retry exhausted. This file's
``_build_agent`` test pins that contract so the next async-signature
change can't silently break goal execution.
"""

from __future__ import annotations

from typing import Any

import pytest

from agents._agent_profiles import AgentProfile
from agents.types import Agent
from tasks._executor import TaskExecutor
from tasks._models import Task


def _stub_agent() -> Agent:
    """Minimal Agent the build_agent stub returns."""
    return Agent(
        name="TASK_AGENT",
        description="",
        instruction="",
        model="",
        options={},
        tools=[],
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_agent_awaits_core_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression guard for the async-signature mismatch.

    ``get_core_tools`` is an async function. ``_build_agent`` must await
    it and pass the resolved list (not the coroutine) to ``AgentState``.
    If a future change drops the ``await`` here, ``list(coroutine)``
    inside ``AgentState.__init__`` raises ``TypeError: 'coroutine'
    object is not iterable`` — the exact failure mode goal runs hit.

    We patch ``get_core_tools`` to an async stub that returns ``[]``,
    so a missing-await regression produces a coroutine handed to
    ``AgentState`` and the test fails with the same TypeError users
    would see. With the await in place, the stub resolves to ``[]``
    and the build completes.
    """
    async def _stub_core_tools() -> list[Any]:
        return []

    profile = AgentProfile(
        id="research_agent",
        name="Research",
        description="",
        skills=[],
        model="stub-model",
    )

    monkeypatch.setattr("tasks._executor.get_core_tools", _stub_core_tools)
    monkeypatch.setattr(
        "tasks._executor.get_agent_profile",
        lambda profile_id: profile if profile_id == "research_agent" else None,
    )
    monkeypatch.setattr(
        "tasks._executor.build_agent",
        lambda profile, tools, name: _stub_agent(),
    )

    task = Task(
        goal_id="g1",
        description="fetch data",
        instruction="do the thing",
        agent_profile="research_agent",
    )
    executor = TaskExecutor(store=None)  # type: ignore[arg-type]

    agent = await executor._build_agent(task)
    assert agent.name == "TASK_AGENT"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_agent_raises_when_task_has_no_profile() -> None:
    """A task without ``agent_profile`` set is a usage error — surface it
    as a clear ``RuntimeError`` rather than letting downstream code
    fail with a confusing AttributeError."""
    task = Task(
        goal_id="g1",
        description="orphan task",
        instruction="do the thing",
        agent_profile=None,
    )
    executor = TaskExecutor(store=None)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="no agent_profile"):
        await executor._build_agent(task)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_agent_raises_when_profile_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Profile lookup miss → ``RuntimeError`` with the missing id named
    in the message, so the error is actionable in goal-run logs."""
    async def _stub_core_tools() -> list[Any]:
        return []

    monkeypatch.setattr("tasks._executor.get_core_tools", _stub_core_tools)
    monkeypatch.setattr("tasks._executor.get_agent_profile", lambda _id: None)

    task = Task(
        goal_id="g1",
        description="task",
        instruction="prompt",
        agent_profile="does_not_exist",
    )
    executor = TaskExecutor(store=None)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="does_not_exist"):
        await executor._build_agent(task)
