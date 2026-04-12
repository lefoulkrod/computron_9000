"""TaskExecutor — bridges TaskResult + Task to the agent turn machinery."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agents.types import Agent, LLMOptions
from config import load_config
from sdk import PersistenceHook, default_hooks, run_turn
from sdk.context import ContextManager, ConversationHistory, LLMCompactionStrategy, ToolClearingStrategy
from sdk.events._context import agent_span, get_current_dispatcher, set_model_options
from sdk.skills.agent_state import AgentState
from sdk.tools._core import get_core_tools
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

        options = self._build_options(task)
        agent = self._build_agent(task, options)
        set_model_options(options)

        history = ConversationHistory(
            [
                {"role": "system", "content": agent.instruction},
                {"role": "user", "content": instruction},
            ],
            instance_id=conversation_id,
        )
        num_ctx = agent.options.get("num_ctx", 0) if agent.options else 0
        ctx_manager = ContextManager(
            history=history,
            context_limit=num_ctx,
            agent_name=agent.name,
            strategies=[ToolClearingStrategy(), LLMCompactionStrategy()],
        )
        hooks = default_hooks(agent, max_iterations=agent.max_iterations, ctx_manager=ctx_manager)
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
            async with agent_span(agent.name, instruction=instruction, agent_state=AgentState(get_core_tools() + (agent.tools or []))):
                result = await run_turn(history, agent, hooks=hooks)

        return result or "", file_paths

    def _build_options(self, task: Task) -> LLMOptions:
        """Build LLMOptions from the task's agent profile or config defaults."""
        if task.agent_profile:
            from agents._agent_profiles import build_llm_options, get_agent_profile
            profile = get_agent_profile(task.agent_profile)
            if profile:
                options = build_llm_options(profile)
                if not options.model:
                    msg = "No model set on profile '%s'" % task.agent_profile
                    raise RuntimeError(msg)
                return options
            logger.warning("Agent profile '%s' not found for task %s, using config defaults",
                           task.agent_profile, task.id)

        # Fall back to goals config defaults
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

    def _build_agent(self, task: Task, options: LLMOptions) -> Agent:
        """Construct an Agent from the task's agent profile."""
        system_prompt = "Complete the task thoroughly. Use save_to_scratchpad to store important results."
        skills_to_load: list[str] = []

        if task.agent_profile:
            from agents._agent_profiles import get_agent_profile
            profile = get_agent_profile(task.agent_profile)
            if profile:
                if profile.system_prompt:
                    system_prompt = profile.system_prompt
                skills_to_load = list(profile.skills)

        loaded = AgentState(get_core_tools())
        for skill_name in skills_to_load:
            loaded.load(skill_name)

        return Agent(
            name="TASK_AGENT",
            description=task.description,
            instruction=system_prompt,
            tools=loaded.tools,
            model=options.model or "",
            think=options.think or False,
            options=options.to_options(),
            max_iterations=options.max_iterations or 0,
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
