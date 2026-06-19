"""TaskExecutor — bridges TaskResult + Task to the agent turn machinery."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agents import build_agent, get_agent_profile
from agents.types import Agent
from sdk import Conversation, TurnExecutor
from sdk.context import ConversationHistory
from sdk.events._models import ContentPayload, FileOutputPayload
from sdk.skills import AgentState, get_skill
from sdk.tools._core import get_core_tools

if TYPE_CHECKING:
    from tasks._models import Goal, Task, TaskResult
    from tasks._store import TaskStore

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Execute a single TaskResult as an agent turn."""

    def __init__(self, store: TaskStore) -> None:
        self._store = store
        self._executor = TurnExecutor()

    async def run(self, task_result: TaskResult, task: Task) -> tuple[str, list[str]]:
        """Execute a task and return (result_text, file_output_paths)."""
        run = self._store.get_run(task_result.run_id)
        if not run:
            msg = f"Run {task_result.run_id} not found"
            raise ValueError(msg)
        goal = self._store.get_goal(run.goal_id)
        if not goal:
            msg = f"Goal {run.goal_id} not found"
            raise ValueError(msg)

        instruction = self._build_instruction(task_result, task, goal)
        conversation_id = f"goals/{run.goal_id}/{run.id}/{task_result.id}"
        self._store.set_conversation_id(task_result.id, conversation_id)

        agent, agent_state = await self._build_agent(task)

        conversation = Conversation(
            id=conversation_id,
            history=ConversationHistory(instance_id=conversation_id),
            agent_state=agent_state,
        )

        accumulated_text: list[str] = []
        file_paths: list[str] = []

        async for event in self._executor.execute(
            conversation=conversation,
            agent=agent,
            user_content=instruction,
        ):
            payload = event.payload
            if isinstance(payload, ContentPayload) and payload.content:
                accumulated_text.append(payload.content)
            elif isinstance(payload, FileOutputPayload) and payload.path:
                file_paths.append(payload.path)

        return "".join(accumulated_text), file_paths

    async def _build_agent(self, task: Task) -> tuple[Agent, AgentState]:
        """Construct an ``Agent`` and matching ``AgentState`` for the task.

        Strict on missing skills: a profile that references an unregistered
        skill fails the task synchronously with a clear message rather than
        running with a silently degraded tool set.
        """
        if not task.agent_profile:
            msg = f"Task {task.id} has no agent_profile set"
            raise RuntimeError(msg)
        profile = get_agent_profile(task.agent_profile)
        if profile is None:
            msg = f"Agent profile '{task.agent_profile}' not found for task {task.id}"
            raise RuntimeError(msg)

        state = AgentState(await get_core_tools())
        for skill_name in profile.skills:
            skill = get_skill(skill_name)
            if skill is None:
                msg = f"Profile '{profile.id}' references unregistered skill '{skill_name}'"
                raise RuntimeError(msg)
            state.add(skill)

        agent = build_agent(profile, tools=state.tools, name="TASK_AGENT")
        return agent, state

    def _build_instruction(
        self, task_result: TaskResult, task: Task, goal: Goal
    ) -> str:
        """Build the agent instruction, injecting predecessor task results."""
        parts = [
            f"## Goal\n{goal.description}\n",
            f"## Task\n{task.instruction}\n",
        ]

        deps = task.depends_on or []
        if deps:
            predecessor_results = self._store.get_completed_results_for_tasks(
                run_id=task_result.run_id,
                task_ids=deps,
            )
            if predecessor_results:
                parts.append("## Results from previous tasks\n")
                for desc, result_text in predecessor_results:
                    parts.append(f"### {desc}\n{result_text}\n")

        return "\n".join(parts)


__all__ = ["TaskExecutor"]
