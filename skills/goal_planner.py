"""Goal planner skill — autonomous goal and task creation."""

from textwrap import dedent

from sdk.skills import Skill
from tasks import add_task, begin_goal, commit_goal, list_goals, list_tasks, trigger_goal

_SKILL = Skill(
    name="goal_planner",
    description="Create and manage autonomous goals with scheduled tasks",
    prompt=dedent("""\
        Build goals using: begin_goal → add_task (once per task) → commit_goal.

        Each add_task call returns the updated draft — pass it into the next call.
        By default each task depends on the previous one (sequential). Pass
        depends_on=[] to run a task in parallel with no dependencies.

        Completed dependency results are automatically appended to a task's
        instruction at execution time — do not use template syntax like {{key}}.

        SKILL SELECTION — each task specifies which skills to load:
        - "browser": web browsing, scraping, form filling
        - "coder": code, files, scripts, analysis
        - Omit skills for a general-purpose agent
        - Combine skills for multi-capability tasks (e.g. ["browser", "coder"])

        Task instructions must be fully self-contained — include all URLs, file
        paths, criteria, and output expectations. The executing agent has no
        other context.

        Use list_goals to see existing goals and list_tasks to inspect a goal's
        tasks. Use trigger_goal to manually run or re-run a goal.
    """),
    tools=[
        begin_goal,
        add_task,
        commit_goal,
        list_goals,
        list_tasks,
        trigger_goal,
    ],
)
