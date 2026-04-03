"""GOAL_PLANNER agent definition.

A dedicated agent that owns goal/task planning tools. COMPUTRON delegates to
it via ``goal_planner_tool``, the same pattern as ``browser_agent_tool``.
"""

from __future__ import annotations

from textwrap import dedent

from sdk import make_run_agent_as_tool_function
from tasks import add_task, begin_goal, commit_goal, list_goals, list_tasks, trigger_goal

NAME = "GOAL_PLANNER"
DESCRIPTION = "Plan and create autonomous goals with scheduled tasks"
SYSTEM_PROMPT = dedent("""
    You are GOAL_PLANNER. Build goals using: begin_goal → add_task (once per task) → commit_goal.

    Each add_task call returns the updated draft — pass it into the next call.
    By default each task depends on the previous one (sequential). Pass
    depends_on=[] to run a task in parallel with no dependencies.

    Completed dependency results are automatically appended to a task's
    instruction at execution time — do not use template syntax like {{key}}.

    AGENT SELECTION:
    - "browser": web browsing, scraping, form filling
    - "coder": code, files, scripts, analysis
    - "computron": general-purpose

    Task instructions must be fully self-contained — include all URLs, file
    paths, criteria, and output expectations. The executing agent has no other
    context.

    Return a summary of the goal and tasks you created.
""")
TOOLS = [
    begin_goal,
    add_task,
    commit_goal,
    list_goals,
    list_tasks,
    trigger_goal,
]

goal_planner_tool = make_run_agent_as_tool_function(
    name=NAME,
    description=DESCRIPTION,
    instruction=SYSTEM_PROMPT,
    tools=TOOLS,
)

__all__ = ["DESCRIPTION", "NAME", "SYSTEM_PROMPT", "TOOLS", "goal_planner_tool"]
