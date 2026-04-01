"""Tests for tasks._tools planning tools."""

import re

import pytest

import tasks
from tasks._tools import create_goal, list_goals, list_tasks

_TASK = {"key": "t1", "description": "task 1", "instruction": "do the thing"}


@pytest.fixture(autouse=True)
def _init_store(tmp_path):
    """Initialize the global store for each test."""
    tasks.init_store(tmp_path / "goals")
    yield
    tasks._store = None


def _extract_id(result_str):
    """Extract id=... from a tool result string."""
    match = re.search(r"id=(\w+)", result_str)
    assert match, f"No id found in: {result_str}"
    return match.group(1)


@pytest.mark.unit
class TestCreateGoal:
    """Test create_goal tool."""

    async def test_one_shot_goal_spawns_run(self):
        """One-shot goal (no cron) auto-spawns a run."""
        result = await create_goal("one shot goal", tasks=[_TASK])
        assert "one shot goal" in result
        goal_id = _extract_id(result)

        store = tasks.get_store()
        runs = store.get_goal_runs(goal_id)
        assert len(runs) == 1

    async def test_recurring_goal_no_auto_run(self):
        """Recurring goal does not auto-spawn a run."""
        result = await create_goal("recurring", tasks=[_TASK], cron="0 */2 * * *")
        goal_id = _extract_id(result)

        store = tasks.get_store()
        runs = store.get_goal_runs(goal_id)
        assert len(runs) == 0

    async def test_empty_description_returns_error(self):
        """Empty description returns an error string."""
        result = await create_goal("", tasks=[_TASK])
        assert "Error" in result

    async def test_empty_tasks_returns_error(self):
        """Empty tasks list returns an error string."""
        result = await create_goal("goal", tasks=[])
        assert "Error" in result

    async def test_bad_cron_returns_error(self):
        """Invalid cron returns an error string."""
        result = await create_goal("goal", tasks=[_TASK], cron="not a cron")
        assert "Error" in result

    async def test_creates_all_tasks(self):
        """All submitted tasks are persisted."""
        tasks_input = [
            {"key": "a", "description": "A", "instruction": "do A"},
            {"key": "b", "description": "B", "instruction": "do B"},
        ]
        result = await create_goal("multi", tasks=tasks_input)
        goal_id = _extract_id(result)

        store = tasks.get_store()
        stored = store.list_tasks(goal_id)
        assert len(stored) == 2
        assert {t.description for t in stored} == {"A", "B"}

    async def test_task_dependencies_resolved(self):
        """depends_on keys are resolved to real task IDs."""
        tasks_input = [
            {"key": "first", "description": "first task", "instruction": "do first"},
            {"key": "second", "description": "second task", "instruction": "do second", "depends_on": ["first"]},
        ]
        result = await create_goal("dep goal", tasks=tasks_input)
        goal_id = _extract_id(result)

        store = tasks.get_store()
        stored = store.list_tasks(goal_id)
        by_desc = {t.description: t for t in stored}
        first_id = by_desc["first task"].id
        assert by_desc["second task"].depends_on == [first_id]

    async def test_task_agent_default(self):
        """Task agent defaults to 'computron' when not specified."""
        result = await create_goal("goal", tasks=[_TASK])
        goal_id = _extract_id(result)

        store = tasks.get_store()
        stored = store.list_tasks(goal_id)
        assert stored[0].agent == "computron"

    async def test_task_agent_override(self):
        """Task agent is set when provided."""
        task = {**_TASK, "agent": "browser"}
        result = await create_goal("goal", tasks=[task])
        goal_id = _extract_id(result)

        store = tasks.get_store()
        stored = store.list_tasks(goal_id)
        assert stored[0].agent == "browser"

    async def test_duplicate_key_returns_error(self):
        """Duplicate task keys return an error without writing anything."""
        tasks_input = [
            {"key": "dup", "description": "A", "instruction": "inst"},
            {"key": "dup", "description": "B", "instruction": "inst"},
        ]
        result = await create_goal("goal", tasks=tasks_input)
        assert "Error" in result

    async def test_unknown_dep_returns_error(self):
        """A depends_on key not in the task list returns an error."""
        tasks_input = [
            {"key": "a", "description": "A", "instruction": "inst", "depends_on": ["nonexistent"]},
        ]
        result = await create_goal("goal", tasks=tasks_input)
        assert "Error" in result

    async def test_forward_dep_returns_error(self):
        """A task may not depend on a key that appears later in the list."""
        tasks_input = [
            {"key": "a", "description": "A", "instruction": "inst", "depends_on": ["b"]},
            {"key": "b", "description": "B", "instruction": "inst"},
        ]
        result = await create_goal("goal", tasks=tasks_input)
        assert "Error" in result

    async def test_missing_task_key_returns_error(self):
        """A task without a key returns an error."""
        result = await create_goal("goal", tasks=[{"description": "A", "instruction": "inst"}])
        assert "Error" in result

    async def test_missing_task_instruction_returns_error(self):
        """A task without instruction returns an error."""
        result = await create_goal("goal", tasks=[{"key": "a", "description": "A"}])
        assert "Error" in result

    async def test_one_shot_run_includes_task_results(self):
        """The auto-spawned run has task results for all tasks, not zero."""
        tasks_input = [
            {"key": "a", "description": "A", "instruction": "do A"},
            {"key": "b", "description": "B", "instruction": "do B"},
        ]
        result = await create_goal("goal", tasks=tasks_input)
        goal_id = _extract_id(result)

        store = tasks.get_store()
        runs = store.get_goal_runs(goal_id)
        assert len(runs) == 1
        task_results = store.get_task_results(runs[0].id)
        assert len(task_results) == 2


@pytest.mark.unit
class TestListTools:
    """Test list_goals and list_tasks tools."""

    async def test_list_goals(self):
        """List goals returns all goals."""
        await create_goal("g1", tasks=[_TASK])
        await create_goal("g2", tasks=[_TASK])
        result = await list_goals()
        assert "g1" in result
        assert "g2" in result

    async def test_list_goals_filtered(self):
        """List goals with status filter."""
        goal_id = _extract_id(await create_goal("g1", tasks=[_TASK]))
        store = tasks.get_store()
        store.set_goal_status(goal_id, "paused")
        result = await list_goals(status="active")
        assert "No goals found" in result

    async def test_list_tasks(self):
        """List tasks for a goal."""
        goal_id = _extract_id(await create_goal("goal", tasks=[_TASK]))
        result = await list_tasks(goal_id)
        assert "task 1" in result

    async def test_timezone_default_to_utc(self):
        """Goal timezone defaults to UTC."""
        result = await create_goal("goal with tz", tasks=[_TASK])
        assert "timezone=UTC" in result

    async def test_timezone_parameter(self):
        """Goal timezone is set when provided."""
        result = await create_goal("goal with tz", tasks=[_TASK], cron="0 * * * *", timezone="America/Chicago")
        assert "timezone=America/Chicago" in result

