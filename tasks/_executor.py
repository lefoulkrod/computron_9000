"""TaskExecutor — bridges TaskResult + Task to the agent turn machinery."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agents.types import Agent, LLMOptions
from config import load_config
from sdk import PersistenceHook, default_hooks, run_turn
from sdk.context import ConversationHistory
from sdk.events._context import agent_span, get_current_dispatcher, set_model_options
from sdk.events._models import FileOutputPayload
from sdk.turn import turn_scope

if TYPE_CHECKING:
    from sdk.events._models import AgentEvent
    from tasks._models import Goal, Task, TaskResult
    from tasks._store import TaskStore

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Execute a single TaskResult as an agent turn."""

    def __init__(self, store: TaskStore) -> None:
        self._store = store
        self._llm_options = self._build_llm_options()

    @staticmethod
    def _build_llm_options() -> LLMOptions:
        """Build LLMOptions from GoalsConfig (called once at init)."""
        cfg = load_config().goals
        if not cfg.model:
            msg = (
                "goals.model is not set in config.yaml. "
                "The task runner needs a model to execute tasks."
            )
            raise RuntimeError(msg)
        return LLMOptions(
            model=cfg.model,
            num_ctx=cfg.num_ctx or None,
            think=cfg.think or None,
            max_iterations=cfg.max_iterations or None,
        )

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
        conversation_id = f"task_{task_result.id}"
        self._store.set_conversation_id(task_result.id, conversation_id)

        options = self._llm_options
        agent = self._build_agent(task, options)
        set_model_options(options)

        history = ConversationHistory([
            {"role": "system", "content": agent.instruction},
            {"role": "user", "content": instruction},
        ])
        hooks = default_hooks(agent, max_iterations=agent.max_iterations)
        hooks.append(
            PersistenceHook(conversation_id=conversation_id, history=history)
        )

        file_paths: list[str] = []

        def _capture_file_output(event: AgentEvent) -> None:
            if isinstance(event.payload, FileOutputPayload) and event.payload.path:
                file_paths.append(event.payload.path)

        async with turn_scope(conversation_id=conversation_id):
            dispatcher = get_current_dispatcher()
            if dispatcher:
                dispatcher.subscribe(_capture_file_output)
            with agent_span(agent.name, instruction=instruction):
                result = await run_turn(history, agent, hooks=hooks)

        return result or "", file_paths

    def _build_agent(self, task: Task, options: LLMOptions) -> Agent:
        """Construct an Agent from registry or inline config."""
        from server.message_handler import _resolve_agent

        if task.agent_config:
            config = task.agent_config
            return Agent(
                name=task.agent,
                description=task.description,
                instruction=config.get("system_prompt", ""),
                tools=[],
                model=options.model or "",
                options=options.to_options(),
            )

        name, desc, prompt, tools = _resolve_agent(task.agent)
        return Agent(
            name=name,
            description=desc,
            instruction=prompt,
            tools=tools,
            model=options.model or "",
            options=options.to_options(),
        )

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
