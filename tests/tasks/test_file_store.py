"""Tests for tasks._file_store.FileTaskStore."""

import pytest

from tasks._file_store import FileTaskStore


@pytest.fixture
def store(tmp_path):
    """Create a FileTaskStore backed by a temp directory."""
    return FileTaskStore(tmp_path / "goals")


@pytest.mark.unit
class TestGoalCRUD:
    """Goal creation, listing, deletion."""

    def test_create_and_get(self, store):
        """Create a goal and retrieve it."""
        goal = store.create_goal("test goal")
        assert goal.description == "test goal"
        assert goal.status == "active"

        retrieved = store.get_goal(goal.id)
        assert retrieved is not None
        assert retrieved.id == goal.id
        assert retrieved.description == goal.description


    def test_create_goal_with_timezone(self, store):
        """Create a goal with a specific timezone."""
        goal = store.create_goal("test goal", cron="0 * * * *", timezone="America/Chicago")
        assert goal.timezone == "America/Chicago"

        retrieved = store.get_goal(goal.id)
        assert retrieved.timezone == "America/Chicago"

    def test_create_goal_timezone_defaults_to_utc(self, store):
        """Goal timezone defaults to UTC when not specified."""
        goal = store.create_goal("test goal")
        assert goal.timezone == "UTC"

        retrieved = store.get_goal(goal.id)
        assert retrieved.timezone == "UTC"

    def test_list_goals(self, store):
        """List all goals."""
        store.create_goal("goal 1")
        store.create_goal("goal 2")
        goals = store.list_goals()
        assert len(goals) == 2

    def test_list_goals_with_status_filter(self, store):
        """List goals filtered by status."""
        g1 = store.create_goal("active goal")
        g2 = store.create_goal("paused goal")
        store.set_goal_status(g2.id, "paused")

        active = store.list_goals(status="active")
        assert len(active) == 1
        assert active[0].id == g1.id

        paused = store.list_goals(status="paused")
        assert len(paused) == 1
        assert paused[0].id == g2.id

    def test_delete_goal(self, store):
        """Delete a goal removes it."""
        goal = store.create_goal("to delete")
        store.delete_goal(goal.id)
        assert store.get_goal(goal.id) is None
        assert store.list_goals() == []

    def test_get_nonexistent_goal(self, store):
        """Getting a nonexistent goal returns None."""
        assert store.get_goal("nonexistent") is None

    def test_set_goal_status(self, store):
        """Pause and resume a goal."""
        goal = store.create_goal("goal")
        store.set_goal_status(goal.id, "paused")
        assert store.get_goal(goal.id).status == "paused"
        store.set_goal_status(goal.id, "active")
        assert store.get_goal(goal.id).status == "active"


@pytest.mark.unit
class TestTaskCRUD:
    """Task creation and listing."""

    def test_create_and_list_tasks(self, store):
        """Create tasks and list them."""
        goal = store.create_goal("goal")
        t1 = store.create_task(
            goal.id, "task 1", "do first", "browser", None, [],
        )
        t2 = store.create_task(
            goal.id, "task 2", "do second", "coder", None, [t1.id],
        )
        tasks = store.list_tasks(goal.id)
        assert len(tasks) == 2
        assert tasks[0].id == t1.id
        assert tasks[1].depends_on == [t1.id]

    def test_get_task(self, store):
        """Get a single task by ID."""
        goal = store.create_goal("goal")
        task = store.create_task(goal.id, "task", "instruction", "coder", None, [])
        found = store.get_task(task.id)
        assert found is not None
        assert found.id == task.id

    def test_get_task_not_found(self, store):
        """Get a nonexistent task returns None."""
        assert store.get_task("no-such-task") is None

    def test_create_task_on_missing_goal(self, store):
        """Creating a task on a nonexistent goal raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            store.create_task("bad-id", "task", "inst", "coder", None, [])


@pytest.mark.unit
class TestRunLifecycle:
    """Run creation, listing, and status updates."""

    def test_spawn_run(self, store):
        """Spawning a run creates task results."""
        # Use recurring goal to avoid auto-spawn on create
        goal = store.create_goal("goal", cron="0 * * * *")
        store.create_task(goal.id, "t1", "prompt", "coder", None, [])
        store.create_task(goal.id, "t2", "prompt", "coder", None, [])

        run = store.spawn_run(goal.id)
        assert run.run_number == 1
        assert run.status == "pending"

        results = store.get_task_results(run.id)
        assert len(results) == 2
        assert all(tr.status == "pending" for tr in results)

    def test_run_number_increments(self, store):
        """Run numbers increment."""
        goal = store.create_goal("goal", cron="0 * * * *")
        store.create_task(goal.id, "t1", "prompt", "coder", None, [])
        r1 = store.spawn_run(goal.id)
        r2 = store.spawn_run(goal.id)
        assert r1.run_number == 1
        assert r2.run_number == 2

    def test_get_run(self, store):
        """Get a run by ID."""
        goal = store.create_goal("goal")
        store.create_task(goal.id, "t", "p", "coder", None, [])
        run = store.spawn_run(goal.id)
        found = store.get_run(run.id)
        assert found is not None
        assert found.id == run.id

    def test_get_run_not_found(self, store):
        """Get a nonexistent run returns None."""
        assert store.get_run("no-such-run") is None

    def test_get_goal_runs(self, store):
        """List runs for a goal."""
        goal = store.create_goal("goal", cron="0 * * * *")
        store.create_task(goal.id, "t", "p", "coder", None, [])
        store.spawn_run(goal.id)
        store.spawn_run(goal.id)
        runs = store.get_goal_runs(goal.id)
        assert len(runs) == 2
        assert runs[0].run_number < runs[1].run_number

    def test_update_run_status_completed(self, store):
        """Run status becomes 'completed' when all tasks complete."""
        goal = store.create_goal("goal")
        t = store.create_task(goal.id, "t", "p", "coder", None, [])
        run = store.spawn_run(goal.id)
        results = store.get_task_results(run.id)

        store.mark_task_result_completed(results[0].id, "done")
        status = store.update_run_status(run.id)
        assert status == "completed"

    def test_update_run_status_failed(self, store):
        """Run status becomes 'failed' when a task fails with no pending."""
        goal = store.create_goal("goal")
        store.create_task(goal.id, "t", "p", "coder", None, [])
        run = store.spawn_run(goal.id)
        results = store.get_task_results(run.id)

        store.mark_task_result_failed(results[0].id, "error")
        status = store.update_run_status(run.id)
        assert status == "failed"

    def test_delete_run(self, store):
        """Delete a run removes it."""
        goal = store.create_goal("goal")
        store.create_task(goal.id, "t", "p", "coder", None, [])
        run = store.spawn_run(goal.id)
        conv_ids = store.delete_run(run.id)
        assert isinstance(conv_ids, list)
        assert store.get_run(run.id) is None

    def test_delete_run_returns_conv_ids(self, store):
        """Delete run returns conversation IDs for cleanup."""
        goal = store.create_goal("goal")
        store.create_task(goal.id, "t", "p", "coder", None, [])
        run = store.spawn_run(goal.id)
        results = store.get_task_results(run.id)
        store.set_conversation_id(results[0].id, "conv-123")

        conv_ids = store.delete_run(run.id)
        assert "conv-123" in conv_ids


@pytest.mark.unit
class TestTaskResultMutations:
    """Task result status transitions."""

    def _setup(self, store):
        """Create a goal with one task and one run."""
        goal = store.create_goal("goal")
        task = store.create_task(goal.id, "t", "p", "coder", None, [])
        run = store.spawn_run(goal.id)
        results = store.get_task_results(run.id)
        return goal, task, run, results[0]

    def test_mark_running(self, store):
        """Mark a task result as running sets started_at."""
        _, _, run, tr = self._setup(store)
        store.mark_task_result_running(tr.id)
        updated = store.get_task_results(run.id)[0]
        assert updated.status == "running"
        assert updated.started_at is not None

    def test_mark_completed(self, store):
        """Mark completed sets result and completed_at."""
        _, _, run, tr = self._setup(store)
        store.mark_task_result_completed(tr.id, "all done")
        updated = store.get_task_results(run.id)[0]
        assert updated.status == "completed"
        assert updated.result == "all done"
        assert updated.completed_at is not None

    def test_mark_failed(self, store):
        """Mark failed sets error and completed_at."""
        _, _, run, tr = self._setup(store)
        store.mark_task_result_failed(tr.id, "boom")
        updated = store.get_task_results(run.id)[0]
        assert updated.status == "failed"
        assert updated.error == "boom"

    def test_increment_retry(self, store):
        """Increment retry bumps count and records error."""
        _, _, run, tr = self._setup(store)
        store.increment_retry(tr.id, "err1")
        updated = store.get_task_results(run.id)[0]
        assert updated.retry_count == 1
        assert updated.error == "err1"

        store.increment_retry(tr.id, "err2")
        updated = store.get_task_results(run.id)[0]
        assert updated.retry_count == 2
        assert updated.error == "err2"

    def test_set_conversation_id(self, store):
        """Set conversation ID on a task result."""
        _, _, run, tr = self._setup(store)
        store.set_conversation_id(tr.id, "conv-abc")
        updated = store.get_task_results(run.id)[0]
        assert updated.conversation_id == "conv-abc"


@pytest.mark.unit
class TestReadyTaskResults:
    """Test get_ready_task_results with dependencies."""

    def test_no_deps_ready_immediately(self, store):
        """Tasks with no deps are ready immediately."""
        goal = store.create_goal("goal")
        store.create_task(goal.id, "t1", "p", "coder", None, [])
        store.spawn_run(goal.id)

        ready = store.get_ready_task_results()
        assert len(ready) == 1
        assert ready[0][1].description == "t1"

    def test_deps_block_until_met(self, store):
        """Tasks with deps are not ready until deps complete."""
        goal = store.create_goal("goal")
        t1 = store.create_task(goal.id, "t1", "p1", "coder", None, [])
        store.create_task(goal.id, "t2", "p2", "coder", None, [t1.id])
        run = store.spawn_run(goal.id)

        # Only t1 should be ready
        ready = store.get_ready_task_results()
        assert len(ready) == 1
        assert ready[0][1].description == "t1"

        # Complete t1, now t2 should be ready
        results = store.get_task_results(run.id)
        t1_result = [r for r in results if r.task_id == t1.id][0]
        store.mark_task_result_completed(t1_result.id, "done")

        ready = store.get_ready_task_results()
        assert len(ready) == 1
        assert ready[0][1].description == "t2"

    def test_paused_goal_excluded(self, store):
        """Paused goals are not included."""
        goal = store.create_goal("goal")
        store.create_task(goal.id, "t1", "p", "coder", None, [])
        store.spawn_run(goal.id)
        store.set_goal_status(goal.id, "paused")

        ready = store.get_ready_task_results()
        assert len(ready) == 0

    def test_completed_run_excluded(self, store):
        """Completed runs don't contribute ready results."""
        goal = store.create_goal("goal")
        store.create_task(goal.id, "t1", "p", "coder", None, [])
        run = store.spawn_run(goal.id)
        results = store.get_task_results(run.id)
        store.mark_task_result_completed(results[0].id, "done")
        store.update_run_status(run.id)

        ready = store.get_ready_task_results()
        assert len(ready) == 0


@pytest.mark.unit
class TestCompletedResultsForTasks:
    """Test get_completed_results_for_tasks."""

    def test_returns_completed_deps(self, store):
        """Returns descriptions and results for completed deps."""
        goal = store.create_goal("goal")
        t1 = store.create_task(goal.id, "Step 1", "do step 1", "coder", None, [])
        t2 = store.create_task(goal.id, "Step 2", "do step 2", "coder", None, [t1.id])
        run = store.spawn_run(goal.id)

        results = store.get_task_results(run.id)
        t1_result = [r for r in results if r.task_id == t1.id][0]
        store.mark_task_result_completed(t1_result.id, "step 1 output")

        completed = store.get_completed_results_for_tasks(run.id, [t1.id])
        assert len(completed) == 1
        assert completed[0] == ("Step 1", "step 1 output")


@pytest.mark.unit
class TestRecovery:
    """Test reset_stale_running."""

    def test_reset_stale_running(self, store):
        """Running task results are reset to pending."""
        goal = store.create_goal("goal")
        store.create_task(goal.id, "t1", "p", "coder", None, [])
        run = store.spawn_run(goal.id)
        results = store.get_task_results(run.id)

        store.mark_task_result_running(results[0].id)
        store.update_run_status(run.id)

        # Simulate restart
        store.reset_stale_running()

        updated = store.get_task_results(run.id)
        assert updated[0].status == "pending"
        assert updated[0].started_at is None

        run_after = store.get_run(run.id)
        assert run_after.status == "pending"


@pytest.mark.unit
class TestCascadeDelete:
    """Test cascade deletion."""

    def test_delete_goal_cascades(self, store):
        """Deleting a goal removes all runs and returns conv IDs."""
        goal = store.create_goal("goal")
        store.create_task(goal.id, "t", "p", "coder", None, [])
        run = store.spawn_run(goal.id)
        results = store.get_task_results(run.id)
        store.set_conversation_id(results[0].id, "conv-xyz")

        conv_ids = store.delete_goal(goal.id)
        assert "conv-xyz" in conv_ids
        assert store.get_goal(goal.id) is None
        assert store.get_goal_runs(goal.id) == []
