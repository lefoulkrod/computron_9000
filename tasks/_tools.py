"""Planning tools for goal and task creation."""

from typing import Any

from tasks import get_store

# Agents valid for use in task definitions (subset of the full agent registry)
_TASK_AGENTS = sorted({"computron", "browser", "coder"})


async def begin_goal(
    description: str,
    cron: str | None = None,
    timezone: str | None = None,
) -> dict[str, Any] | str:
    """Begin building a new goal draft.

    Returns a draft dict to pass to add_task and commit_goal.

    Args:
        description: What this goal accomplishes.
        cron: Optional cron expression for recurring goals (e.g. '0 10 * * *').
        timezone: IANA timezone name (e.g. 'America/Chicago'). Defaults to UTC.
    """
    if not description or not description.strip():
        return "Error: description is required."
    if cron:
        try:
            from croniter import croniter

            croniter(cron)
        except (ValueError, KeyError):
            return f"Error: Invalid cron expression '{cron}'."
    if timezone:
        try:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, KeyError):
            return f"Error: Unknown timezone '{timezone}'. Use an IANA timezone name (e.g. 'America/Chicago', 'UTC')."
    draft: dict[str, Any] = {"description": description.strip(), "tasks": []}
    if cron:
        draft["cron"] = cron
    if timezone:
        draft["timezone"] = timezone
    return draft


async def add_task(
    draft: dict[str, Any],
    key: str,
    description: str,
    instruction: str,
    agent: str = "computron",
    depends_on: list[str] | None = None,
) -> dict[str, Any] | str:
    """Add a task to a goal draft and return the updated draft.

    Omit depends_on to automatically depend on the previous task (sequential).
    Pass depends_on=[] to run immediately with no dependencies (parallel).

    Args:
        draft: Current goal draft from begin_goal or a previous add_task.
        key: Unique short identifier for this task (e.g. 'fetch_data').
        description: Short human-readable description.
        instruction: Full self-contained agent prompt.
        agent: 'computron' (default), 'browser', or 'coder'.
        depends_on: Keys of tasks this task depends on. Omit to depend on the
            previous task. Pass [] for no dependencies (parallel execution).
    """
    if not isinstance(draft, dict) or "tasks" not in draft:
        return "Error: invalid draft. Start with begin_goal."
    if not key or not key.strip():
        return "Error: key is required."
    key = key.strip()
    existing_keys = [t["key"] for t in draft["tasks"]]
    if key in existing_keys:
        return f"Error: duplicate key '{key}'. Existing keys: {existing_keys}."
    if not description or not description.strip():
        return f"Error: description is required for task '{key}'."
    if not instruction or not instruction.strip():
        return f"Error: instruction is required for task '{key}'."
    if agent not in _TASK_AGENTS:
        return f"Error: unknown agent '{agent}' for task '{key}'. Valid agents: {_TASK_AGENTS}."

    # Default to previous task if depends_on is omitted and one exists
    resolved_deps = [existing_keys[-1]] if depends_on is None and existing_keys else (depends_on or [])

    for dep in resolved_deps:
        if dep not in existing_keys:
            return f"Error: depends_on '{dep}' not found. Known keys: {existing_keys}."

    task: dict[str, Any] = {
        "key": key,
        "description": description.strip(),
        "instruction": instruction.strip(),
        "agent": agent,
        "depends_on": resolved_deps,
    }
    return {**draft, "tasks": [*draft["tasks"], task]}


async def commit_goal(draft: dict[str, Any]) -> str:
    """Validate and save a completed goal draft to disk.

    Args:
        draft: The goal draft built with begin_goal and add_task.
    """
    if not isinstance(draft, dict):
        return "Error: invalid draft."
    return await create_goal(
        description=draft.get("description", ""),
        tasks=draft.get("tasks", []),
        cron=draft.get("cron"),
        timezone=draft.get("timezone"),
    )


async def create_goal(
    description: str,
    tasks: list[dict[str, Any]],
    cron: str | None = None,
    timezone: str | None = None,
) -> str:
    """Create a goal with all its tasks in a single call.

    Each task must have a unique ``key`` used to express dependencies within
    this submission. ``depends_on`` lists keys of tasks that must complete
    before this one starts. Tasks without ``depends_on`` run in parallel
    immediately.

    Example::

        create_goal(
            description="Research and summarize today's AI news",
            tasks=[
                {
                    "key": "research",
                    "description": "Find today's top AI news stories",
                    "instruction": "Browse news sites and find the top 5 AI stories published today. Return headlines, sources, and URLs.",
                    "agent": "browser",
                },
                {
                    "key": "summarize",
                    "description": "Write a summary of the research",
                    "instruction": "Summarize the AI news stories from the research task into a concise briefing.",
                    "agent": "coder",
                    "depends_on": ["research"],
                },
            ],
        )

    Args:
        description: What this goal accomplishes.
        tasks: List of task definitions. Each item must have:
            - key (str): Local reference key, used in other tasks' depends_on.
            - description (str): Short human-readable description.
            - instruction (str): Full, self-contained agent prompt. The
              executing agent has no conversation history — include all URLs,
              file paths, criteria, and output expectations.
            - agent (str, optional): 'computron' (default), 'browser', or
              'coder'.
            - agent_config (dict, optional): Inline agent override with
              'system_prompt' and/or 'tools'.
            - depends_on (list[str], optional): Keys of tasks this task
              depends on.
        cron: Cron expression for recurring goals (e.g. '0 */2 * * *').
            Omit for one-shot goals, which spawn a run immediately.
        timezone: IANA timezone name (e.g. 'America/Chicago', 'UTC').
            Uses the config default if not specified.
    """
    if not description or not description.strip():
        return "Error: description is required and cannot be empty."
    if not tasks:
        return "Error: tasks is required and cannot be empty. Define at least one task."
    if cron:
        try:
            from croniter import croniter

            croniter(cron)
        except (ValueError, KeyError):
            return f"Error: Invalid cron expression '{cron}'. Use standard 5-field cron syntax (e.g. '0 */2 * * *')."

    seen_keys: set[str] = set()
    for i, t in enumerate(tasks):
        key = t.get("key")
        if not key or not str(key).strip():
            return f"Error: tasks[{i}] is missing a 'key'."
        key = str(key).strip()
        if key in seen_keys:
            return f"Error: Duplicate task key '{key}'. Each task must have a unique key."
        seen_keys.add(key)
        if not t.get("description") or not str(t["description"]).strip():
            return f"Error: tasks[{i}] (key='{key}') is missing 'description'."
        if not t.get("instruction") or not str(t["instruction"]).strip():
            return f"Error: tasks[{i}] (key='{key}') is missing 'instruction'."
        for dep in t.get("depends_on") or []:
            if dep not in seen_keys:
                return (
                    f"Error: tasks[{i}] (key='{key}') depends_on '{dep}' which is not"
                    f" defined before it. List tasks in execution order and only"
                    f" reference keys of earlier tasks."
                )

    store = get_store()
    goal = store.create_goal(
        description=description.strip(),
        cron=cron,
        timezone=timezone,
        auto_run=False,
    )

    key_to_id: dict[str, str] = {}
    from tasks._models import _new_id

    task_defs: list[dict] = []
    for t in tasks:
        key = str(t["key"]).strip()
        dep_keys = t.get("depends_on") or []
        task_id = _new_id()
        key_to_id[key] = task_id
        task_defs.append({
            "id": task_id,
            "description": str(t["description"]).strip(),
            "instruction": str(t["instruction"]).strip(),
            "agent": t.get("agent", "computron"),
            "agent_config": t.get("agent_config"),
            "depends_on": [key_to_id[k] for k in dep_keys],
        })

    created_tasks = store.create_tasks(goal_id=goal.id, task_defs=task_defs)

    if not cron:
        store.spawn_run(goal.id)

    lines = []
    keys = [str(t["key"]).strip() for t in tasks]
    for key, task in zip(keys, created_tasks):
        dep_keys = tasks[keys.index(key)].get("depends_on") or []
        deps_note = f", depends_on={dep_keys}" if dep_keys else ""
        lines.append(f"  - [{key}] {task.description} (id={task.id}, agent={task.agent}{deps_note})")

    task_lines = "\n".join(lines)
    tz_note = f", timezone={goal.timezone}" if goal.timezone else ""
    return f"Created goal '{goal.description}' (id={goal.id}{tz_note}) with {len(created_tasks)} task(s):\n{task_lines}"


async def list_goals(status: str | None = None) -> str:
    """List goals, optionally filtered by status.

    Args:
        status: Filter by goal status ('active' or 'paused'). Omit for all.
    """
    store = get_store()
    goals = store.list_goals(status=status)
    if not goals:
        return "No goals found."
    lines = [f"- {g.description} (id={g.id}, status={g.status}, cron={g.cron}, timezone={g.timezone})" for g in goals]
    return "\n".join(lines)


async def list_tasks(goal_id: str) -> str:
    """List task definitions for a goal.

    Args:
        goal_id: The goal to list tasks for.
    """
    if not goal_id or not goal_id.strip():
        return "Error: goal_id is required."
    store = get_store()
    tasks = store.list_tasks(goal_id)
    if not tasks:
        return "No tasks found for this goal."
    lines = [f"- {t.description} (id={t.id}, agent={t.agent}, depends_on={t.depends_on})" for t in tasks]
    return "\n".join(lines)


async def trigger_goal(goal_id: str) -> str:
    """Manually trigger a new run for a goal, regardless of its cron schedule.

    Args:
        goal_id: The goal to trigger.
    """
    if not goal_id or not goal_id.strip():
        return "Error: goal_id is required."
    store = get_store()
    goal = store.get_goal(goal_id)
    if not goal:
        return f"Error: Goal '{goal_id}' not found."
    run = store.spawn_run(goal_id)
    return f"Triggered run #{run.run_number} (id={run.id}) for goal '{goal.description}'."


__all__ = ["add_task", "begin_goal", "commit_goal", "create_goal", "list_goals", "list_tasks", "trigger_goal"]
