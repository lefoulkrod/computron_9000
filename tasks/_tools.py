"""Planning tools for goal and task creation."""

from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

from agents import (
    get_agent_profile,
    list_agent_profiles,
)
from tasks._models import _new_id
from tasks._singleton import get_store


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
            croniter(cron)
        except (ValueError, KeyError):
            return f"Error: Invalid cron expression '{cron}'."
    if timezone:
        try:
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
    agent_profile: str,
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
        agent_profile: Agent profile ID (e.g. 'code_expert', 'research_agent').
            Call list_agent_profiles() to see available profiles.
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
    if not agent_profile or not agent_profile.strip():
        available = [p.id for p in list_agent_profiles()]
        return f"Error: agent_profile is required for task '{key}'. Available: {available}."

    resolved = get_agent_profile(agent_profile)
    if resolved is None:
        available = [p.id for p in list_agent_profiles()]
        return f"Error: unknown agent profile '{agent_profile}' for task '{key}'. Available: {available}."
    if not resolved.enabled:
        available = [p.id for p in list_agent_profiles()]
        return (
            f"Error: agent profile '{agent_profile}' is disabled and cannot be used "
            f"for task '{key}'. Available: {available}."
        )

    # Default to previous task if depends_on is omitted and one exists
    resolved_deps = [existing_keys[-1]] if depends_on is None and existing_keys else (depends_on or [])

    for dep in resolved_deps:
        if dep not in existing_keys:
            return f"Error: depends_on '{dep}' not found. Known keys: {existing_keys}."

    task: dict[str, Any] = {
        "key": key,
        "description": description.strip(),
        "instruction": instruction.strip(),
        "depends_on": resolved_deps,
        "agent_profile": agent_profile,
    }
    return {**draft, "tasks": [*draft["tasks"], task]}


async def commit_goal(draft: dict[str, Any]) -> str:
    """Validate and save a completed goal draft to disk.

    Args:
        draft: The goal draft built with begin_goal and add_task.
    """
    if not isinstance(draft, dict):
        return "Error: invalid draft."
    description = draft.get("description", "")
    tasks = draft.get("tasks", [])
    cron = draft.get("cron")
    timezone = draft.get("timezone")

    if not description or not description.strip():
        return "Error: description is required and cannot be empty."
    if not tasks:
        return "Error: tasks is required and cannot be empty. Define at least one task."
    if cron:
        try:
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
        requested = t.get("agent_profile")
        if not requested:
            return f"Error: tasks[{i}] (key='{key}') is missing 'agent_profile'."
        resolved = get_agent_profile(requested)
        if resolved is None:
            available = [p.id for p in list_agent_profiles()]
            return (
                f"Error: tasks[{i}] (key='{key}') references unknown agent profile "
                f"'{requested}'. Available: {available}."
            )
        if not resolved.enabled:
            available = [p.id for p in list_agent_profiles()]
            return (
                f"Error: tasks[{i}] (key='{key}') references disabled agent profile "
                f"'{requested}'. Available: {available}."
            )

    store = get_store()
    goal = store.create_goal(
        description=description.strip(),
        cron=cron,
        timezone=timezone,
        auto_run=False,
    )

    key_to_id: dict[str, str] = {}
    task_defs: list[dict] = []
    for t in tasks:
        key = str(t["key"]).strip()
        dep_keys = t.get("depends_on") or []
        task_id = _new_id()
        key_to_id[key] = task_id
        task_def: dict[str, Any] = {
            "id": task_id,
            "description": str(t["description"]).strip(),
            "instruction": str(t["instruction"]).strip(),
            "depends_on": [key_to_id[k] for k in dep_keys],
            "agent_profile": t["agent_profile"],
        }
        task_defs.append(task_def)

    created_tasks = store.create_tasks(goal_id=goal.id, task_defs=task_defs)

    if not cron:
        store.queue_run(goal.id)

    lines = []
    keys = [str(t["key"]).strip() for t in tasks]
    for key, task in zip(keys, created_tasks, strict=True):
        dep_keys = tasks[keys.index(key)].get("depends_on") or []
        deps_note = f", depends_on={dep_keys}" if dep_keys else ""
        profile_note = f", profile={task.agent_profile}" if task.agent_profile else ""
        lines.append(f"  - [{key}] {task.description} (id={task.id}{profile_note}{deps_note})")

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
    lines = [f"- {t.description} (id={t.id}, profile={t.agent_profile}, depends_on={t.depends_on})" for t in tasks]
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
    run = store.queue_run(goal_id)
    return f"Triggered run #{run.run_number} (id={run.id}) for goal '{goal.description}'."


__all__ = ["add_task", "begin_goal", "commit_goal", "list_goals", "list_tasks", "trigger_goal"]
