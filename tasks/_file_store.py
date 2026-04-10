"""File-based TaskStore implementation using JSON files on disk."""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Callable
from pathlib import Path

from tasks._models import Goal, Run, Task, TaskResult, _new_id, _utcnow
from tasks._scheduler import cron_has_fired_since

logger = logging.getLogger(__name__)


class FileTaskStore:
    """File-based TaskStore implementation.

    One JSON file per goal (containing task definitions), one JSON file per
    run (containing task results). Layout::

        {base_dir}/
        ├── {goal_id}.json
        └── {goal_id}/
            └── runs/
                └── {run_id}.json
    """

    def __init__(self, base_dir: Path, default_timezone: str = "UTC") -> None:
        self._base = base_dir
        self._base.mkdir(parents=True, exist_ok=True)
        self._default_timezone = default_timezone


    def _goal_path(self, goal_id: str) -> Path:
        return self._base / f"{goal_id}.json"

    def _runs_dir(self, goal_id: str) -> Path:
        return self._base / goal_id / "runs"

    def _run_path(self, goal_id: str, run_id: str) -> Path:
        return self._runs_dir(goal_id) / f"{run_id}.json"


    @staticmethod
    def _goal_from_data(data: dict) -> "Goal":
        return Goal(**{k: v for k, v in data.items() if k != "tasks"})

    @staticmethod
    def _run_from_data(data: dict) -> "Run":
        return Run(**{k: v for k, v in data.items() if k != "task_results"})


    def _write_json(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        tmp.replace(path)

    def _read_json(self, path: Path) -> dict | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


    def create_goal(self, description: str, cron: str | None = None, timezone: str | None = None, auto_run: bool = True) -> Goal:
        """Create a new goal. One-shot goals (no cron) auto-spawn a run unless auto_run=False."""
        goal = Goal(description=description, cron=cron, timezone=timezone or self._default_timezone)
        data = goal.model_dump()
        data["tasks"] = []
        self._write_json(self._goal_path(goal.id), data)
        if auto_run and not cron:
            self.queue_run(goal.id)
        return goal

    def get_goal(self, goal_id: str) -> Goal | None:
        """Return a goal by ID, or None if not found."""
        data = self._read_json(self._goal_path(goal_id))
        if not data:
            return None
        return self._goal_from_data(data)

    def list_goals(self, status: str | None = None) -> list[Goal]:
        """List goals, optionally filtered by status."""
        goals = []
        for p in self._base.glob("*.json"):
            data = self._read_json(p)
            if data and (status is None or data.get("status") == status):
                goals.append(self._goal_from_data(data))
        return sorted(goals, key=lambda g: g.created_at, reverse=True)

    def set_goal_status(self, goal_id: str, status: str) -> None:
        """Update the status of a goal."""
        path = self._goal_path(goal_id)
        data = self._read_json(path)
        if data:
            data["status"] = status
            self._write_json(path, data)

    def delete_goal(self, goal_id: str) -> list[str]:
        """Delete goal and all runs. Returns conversation_ids for cleanup."""
        conv_ids: list[str] = []
        runs_dir = self._runs_dir(goal_id)
        if runs_dir.exists():
            for rp in runs_dir.glob("*.json"):
                run_data = self._read_json(rp)
                if run_data:
                    for tr in run_data.get("task_results", []):
                        if tr.get("conversation_id"):
                            conv_ids.append(tr["conversation_id"])
        goal_dir = self._base / goal_id
        if goal_dir.exists():
            shutil.rmtree(goal_dir)
        self._goal_path(goal_id).unlink(missing_ok=True)
        return conv_ids


    def create_task(
        self,
        goal_id: str,
        description: str,
        instruction: str,
        skills_or_agent: str | list[str] = "",
        agent_config: dict | None = None,
        depends_on: list[str] | None = None,
    ) -> Task:
        """Create a task definition belonging to a goal.

        ``skills_or_agent`` accepts either a list of skill names or a
        legacy agent string (for backward compatibility with tests).
        """
        if isinstance(skills_or_agent, str):
            # Legacy compat: map old agent names to skill lists
            agent_to_skills: dict[str, list[str]] = {
                "browser": ["browser"],
                "coder": ["coder"],
                "computron": [],
            }
            skills = agent_to_skills.get(skills_or_agent, [])
        else:
            skills = skills_or_agent
        return self.create_tasks(goal_id, [{
            "description": description,
            "instruction": instruction,
            "skills": skills,
            "agent_config": agent_config,
            "depends_on": depends_on or [],
        }])[0]

    def create_tasks(
        self,
        goal_id: str,
        task_defs: list[dict],
    ) -> list[Task]:
        """Create multiple task definitions in a single read-write cycle."""
        path = self._goal_path(goal_id)
        data = self._read_json(path)
        if not data:
            msg = f"Goal {goal_id} not found"
            raise ValueError(msg)
        created: list[Task] = []
        for td in task_defs:
            task = Task(goal_id=goal_id, **td)
            data["tasks"].append(task.model_dump())
            created.append(task)
        self._write_json(path, data)
        return created

    @staticmethod
    def _migrate_task_data(t: dict) -> dict:
        """Migrate legacy task data that used 'agent' to 'skills'."""
        if "agent" in t and "skills" not in t:
            agent = t.pop("agent")
            # Map old agent names to skill lists
            agent_to_skills: dict[str, list[str]] = {
                "browser": ["browser"],
                "coder": ["coder"],
                "computron": [],
            }
            t["skills"] = agent_to_skills.get(agent, [])
        return t

    def list_tasks(self, goal_id: str) -> list[Task]:
        """List task definitions for a goal."""
        data = self._read_json(self._goal_path(goal_id))
        if not data:
            return []
        return [Task(**self._migrate_task_data(t)) for t in data.get("tasks", [])]

    def get_task(self, task_id: str) -> Task | None:
        """Return a task by ID, or None if not found."""
        for p in self._base.glob("*.json"):
            data = self._read_json(p)
            if data:
                for t in data.get("tasks", []):
                    if t.get("id") == task_id:
                        return Task(**t)
        return None


    def queue_run(self, goal_id: str) -> Run:
        """Create a new run for a goal with TaskResults for each task."""
        existing = self.get_goal_runs(goal_id)
        run_number = max((r.run_number for r in existing), default=0) + 1

        run = Run(goal_id=goal_id, run_number=run_number)
        tasks = self.list_tasks(goal_id)
        task_results = [
            TaskResult(run_id=run.id, task_id=t.id).model_dump()
            for t in tasks
        ]

        run_data = run.model_dump()
        run_data["task_results"] = task_results
        self._write_json(self._run_path(goal_id, run.id), run_data)
        return run

    def stamp_last_run_spawned(self, goal_id: str) -> None:
        """Update the goal's last_run_spawned_at timestamp.

        Called by the scheduler when spawning a cron-triggered run so the
        anchor survives run deletion. Manual triggers should NOT call this.
        """
        path = self._goal_path(goal_id)
        data = self._read_json(path)
        if data:
            data["last_run_spawned_at"] = _utcnow()
            self._write_json(path, data)

    def get_run(self, run_id: str) -> Run | None:
        """Return a run by ID, or None if not found."""
        try:
            _, run_data, _ = self._find_run(run_id)
            return self._run_from_data(run_data)
        except ValueError:
            return None

    def get_goal_runs(self, goal_id: str) -> list[Run]:
        """List all runs for a goal."""
        runs_dir = self._runs_dir(goal_id)
        if not runs_dir.exists():
            return []
        runs = []
        for p in runs_dir.glob("*.json"):
            data = self._read_json(p)
            if data:
                runs.append(self._run_from_data(data))
        return sorted(runs, key=lambda r: r.run_number)

    def update_run_status(self, run_id: str) -> str:
        """Recompute run status from its task_results."""
        goal_id, run_data, run_path = self._find_run(run_id)
        task_results = run_data.get("task_results", [])

        # Cascade failures: if a pending task's dependency has failed, fail it too.
        # Loop until no more cascades are possible.
        tasks = {t.id: t for t in self.list_tasks(goal_id)}
        changed = True
        while changed:
            changed = False
            failed_task_ids = {tr["task_id"] for tr in task_results if tr["status"] == "failed"}
            for tr in task_results:
                if tr["status"] != "pending":
                    continue
                task = tasks.get(tr["task_id"])
                if task and any(dep in failed_task_ids for dep in task.depends_on):
                    tr["status"] = "failed"
                    tr["error"] = "Blocked: a dependency task failed"
                    tr["completed_at"] = _utcnow()
                    changed = True

        statuses = [tr["status"] for tr in task_results]

        if all(s == "completed" for s in statuses):
            new_status = "completed"
        elif any(s == "failed" for s in statuses) and not any(
            s in ("pending", "running") for s in statuses
        ):
            new_status = "failed"
        elif any(s == "running" for s in statuses):
            new_status = "running"
        else:
            new_status = "pending"

        run_data["status"] = new_status
        if new_status == "running" and not run_data.get("started_at"):
            run_data["started_at"] = _utcnow()
        if new_status in ("completed", "failed"):
            run_data["completed_at"] = _utcnow()
        self._write_json(run_path, run_data)
        return new_status

    def delete_run(self, run_id: str) -> list[str]:
        """Delete run and task_results. Returns conversation_ids for cleanup."""
        for goal_dir in self._base.iterdir():
            if not goal_dir.is_dir():
                continue
            run_path = goal_dir / "runs" / f"{run_id}.json"
            if run_path.exists():
                data = self._read_json(run_path)
                conv_ids = [
                    tr["conversation_id"]
                    for tr in data.get("task_results", [])
                    if tr.get("conversation_id")
                ]
                run_path.unlink()
                return conv_ids
        return []


    def get_task_results(self, run_id: str) -> list[TaskResult]:
        """Get all task results for a run."""
        try:
            _, run_data, _ = self._find_run(run_id)
        except ValueError:
            return []
        return [TaskResult(**tr) for tr in run_data.get("task_results", [])]

    def get_ready_task_results(self) -> list[tuple[TaskResult, Task]]:
        """Scan all active goals' in-progress runs for pending results with deps met."""
        ready: list[tuple[TaskResult, Task]] = []
        for goal in self.list_goals(status="active"):
            tasks = {t.id: t for t in self.list_tasks(goal.id)}
            for run in self.get_goal_runs(goal.id):
                if run.status not in ("pending", "running"):
                    continue
                run_data = self._read_json(self._run_path(goal.id, run.id))
                if not run_data:
                    continue
                results = run_data.get("task_results", [])
                completed_task_ids = {
                    tr["task_id"] for tr in results if tr["status"] == "completed"
                }
                for tr_data in results:
                    if tr_data["status"] != "pending":
                        continue
                    task = tasks.get(tr_data["task_id"])
                    if not task:
                        continue
                    if all(dep_id in completed_task_ids for dep_id in task.depends_on):
                        ready.append((TaskResult(**tr_data), task))
        return ready

    def mark_task_result_running(self, result_id: str) -> None:
        """Mark a task result as running."""
        self._mutate_task_result(
            result_id,
            lambda tr: tr.update(status="running", started_at=_utcnow()),
        )

    def mark_task_result_completed(self, result_id: str, result: str) -> None:
        """Mark a task result as completed with its result text."""
        self._mutate_task_result(
            result_id,
            lambda tr: tr.update(status="completed", result=result, completed_at=_utcnow()),
        )

    def mark_task_result_failed(self, result_id: str, error: str) -> None:
        """Mark a task result as failed with an error message."""
        self._mutate_task_result(
            result_id,
            lambda tr: tr.update(status="failed", error=error, completed_at=_utcnow()),
        )

    def increment_retry(self, result_id: str, error: str) -> None:
        """Increment retry count and record the error."""
        self._mutate_task_result(
            result_id,
            lambda tr: tr.update(retry_count=tr.get("retry_count", 0) + 1, error=error),
        )

    def update_task_result_status(self, result_id: str, status: str) -> None:
        """Update the status of a task result."""
        self._mutate_task_result(
            result_id,
            lambda tr: tr.update(status=status),
        )

    def set_conversation_id(self, result_id: str, conversation_id: str) -> None:
        """Set the conversation ID for a task result."""
        self._mutate_task_result(
            result_id,
            lambda tr: tr.update(conversation_id=conversation_id),
        )

    def set_file_outputs(self, result_id: str, file_outputs: list[str]) -> None:
        """Set the file output paths for a task result."""
        self._mutate_task_result(
            result_id,
            lambda tr: tr.update(file_outputs=file_outputs),
        )

    def get_completed_results_for_tasks(
        self, run_id: str, task_ids: list[str]
    ) -> list[tuple[str, str]]:
        """Returns (task.description, result_text) for completed deps in a run."""
        goal_id, run_data, _ = self._find_run(run_id)
        tasks = {t.id: t for t in self.list_tasks(goal_id)}
        results: list[tuple[str, str]] = []
        for tr in run_data.get("task_results", []):
            if (
                tr["task_id"] in task_ids
                and tr["status"] == "completed"
                and tr.get("result")
            ):
                task = tasks.get(tr["task_id"])
                if task:
                    results.append((task.description, tr["result"]))
        return results


    def get_due_recurring_goals(self) -> list[Goal]:
        """Active goals with cron, no in-progress run, and cron due since last run."""
        result: list[Goal] = []
        for goal in self.list_goals(status="active"):
            if not goal.cron:
                continue
            runs = self.get_goal_runs(goal.id)
            # Skip if any run is still in progress
            if any(r.status in ("pending", "running") for r in runs):
                continue
            last_completed = max(
                (r.completed_at for r in runs if r.completed_at), default=None
            )
            anchor = last_completed or goal.last_run_spawned_at or goal.created_at
            if cron_has_fired_since(goal.cron, anchor, goal.timezone):
                result.append(goal)
        return result


    def reset_stale_running(self) -> None:
        """Reset task_results stuck in 'running' back to 'pending', then cascade failures."""
        for goal_dir in self._base.iterdir():
            if not goal_dir.is_dir():
                continue
            runs_dir = goal_dir / "runs"
            if not runs_dir.exists():
                continue
            tasks = {t.id: t for t in self.list_tasks(goal_dir.name)}
            for run_path in runs_dir.glob("*.json"):
                data = self._read_json(run_path)
                if not data:
                    continue
                if data.get("status") not in ("pending", "running"):
                    continue
                changed = False
                for tr in data.get("task_results", []):
                    if tr["status"] == "running":
                        tr["status"] = "pending"
                        tr["started_at"] = None
                        changed = True

                # Cascade failures for pending tasks whose deps have failed.
                task_results = data.get("task_results", [])
                cascade = True
                while cascade:
                    cascade = False
                    failed_ids = {tr["task_id"] for tr in task_results if tr["status"] == "failed"}
                    for tr in task_results:
                        if tr["status"] != "pending":
                            continue
                        task = tasks.get(tr["task_id"])
                        if task and any(dep in failed_ids for dep in task.depends_on):
                            tr["status"] = "failed"
                            tr["error"] = "Blocked: a dependency task failed"
                            tr["completed_at"] = _utcnow()
                            changed = True
                            cascade = True

                if changed:
                    # Recompute run status
                    statuses = [tr["status"] for tr in task_results]
                    if all(s == "completed" for s in statuses):
                        data["status"] = "completed"
                    elif any(s == "failed" for s in statuses) and not any(
                        s in ("pending", "running") for s in statuses
                    ):
                        data["status"] = "failed"
                        if not data.get("completed_at"):
                            data["completed_at"] = _utcnow()
                    elif any(s == "running" for s in statuses):
                        data["status"] = "running"
                    else:
                        data["status"] = "pending"
                    self._write_json(run_path, data)


    def _find_run(self, run_id: str) -> tuple[str, dict, Path]:
        """Locate a run file by run_id.

        Returns:
            Tuple of (goal_id, run_data, run_path).

        Raises:
            ValueError: If the run is not found.
        """
        for goal_dir in self._base.iterdir():
            if not goal_dir.is_dir():
                continue
            run_path = goal_dir / "runs" / f"{run_id}.json"
            if run_path.exists():
                data = self._read_json(run_path)
                if data is not None:
                    return goal_dir.name, data, run_path
        raise ValueError(f"Run {run_id} not found")

    def _mutate_task_result(self, result_id: str, fn: Callable[[dict], None]) -> None:
        """Find a task_result by ID across all runs, apply mutation, save."""
        for goal_dir in self._base.iterdir():
            if not goal_dir.is_dir():
                continue
            runs_dir = goal_dir / "runs"
            if not runs_dir.exists():
                continue
            for run_path in runs_dir.glob("*.json"):
                data = self._read_json(run_path)
                if not data:
                    continue
                for tr in data.get("task_results", []):
                    if tr["id"] == result_id:
                        fn(tr)
                        self._write_json(run_path, data)
                        return


__all__ = ["FileTaskStore"]
