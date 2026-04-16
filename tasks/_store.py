"""TaskStore protocol — abstract store interface for the task engine."""

from __future__ import annotations

from typing import Protocol

from tasks._models import Goal, Run, Task, TaskResult


class TaskStore(Protocol):
    """Abstract store interface for goals, tasks, runs, and task results.

    All methods are synchronous. The store is designed to be swapped from
    file-based to SQLite (or another backend) by implementing this protocol.
    """

    def create_goal(
        self,
        description: str,
        cron: str | None = None,
        timezone: str | None = None,
        auto_run: bool = True,
    ) -> Goal:
        """Create a new goal. One-shot goals (no cron) auto-spawn a run unless auto_run=False."""
        ...

    def get_goal(self, goal_id: str) -> Goal | None:
        """Return a goal by ID, or None if not found."""
        ...

    def list_goals(self, status: str | None = None) -> list[Goal]:
        """List goals, optionally filtered by status."""
        ...

    def set_goal_status(self, goal_id: str, status: str) -> None:
        """Update the status of a goal."""
        ...

    def delete_goal(self, goal_id: str) -> list[str]:
        """Delete goal and all runs. Returns conversation_ids for cleanup."""
        ...

    def create_task(
        self,
        goal_id: str,
        description: str,
        instruction: str,
        agent_profile: str | None = None,
        depends_on: list[str] | None = None,
    ) -> Task:
        """Create a task definition belonging to a goal."""
        ...

    def create_tasks(
        self,
        goal_id: str,
        task_defs: list[dict],
    ) -> list[Task]:
        """Create multiple task definitions in a single read-write cycle."""
        ...

    def list_tasks(self, goal_id: str) -> list[Task]:
        """List task definitions for a goal."""
        ...

    def get_task(self, task_id: str) -> Task | None:
        """Return a task by ID, or None if not found."""
        ...

    def queue_run(self, goal_id: str) -> Run:
        """Create a new run for a goal with TaskResults for each task."""
        ...

    def get_run(self, run_id: str) -> Run | None:
        """Return a run by ID, or None if not found."""
        ...

    def get_goal_runs(self, goal_id: str) -> list[Run]:
        """List all runs for a goal."""
        ...

    def update_run_status(self, run_id: str) -> str:
        """Recompute run status from task_results. Returns new status."""
        ...

    def delete_run(self, run_id: str) -> list[str]:
        """Delete run and task_results. Returns conversation_ids for cleanup."""
        ...

    def get_task_results(self, run_id: str) -> list[TaskResult]:
        """Get all task results for a run."""
        ...

    def get_ready_task_results(self) -> list[tuple[TaskResult, Task]]:
        """Pending results whose deps are met, in active runs of active goals."""
        ...

    def mark_task_result_running(self, result_id: str) -> None:
        """Mark a task result as running."""
        ...

    def mark_task_result_completed(self, result_id: str, result: str) -> None:
        """Mark a task result as completed with its result text."""
        ...

    def mark_task_result_failed(self, result_id: str, error: str) -> None:
        """Mark a task result as failed with an error message."""
        ...

    def increment_retry(self, result_id: str, error: str) -> None:
        """Increment retry count and record the error."""
        ...

    def update_task_result_status(self, result_id: str, status: str) -> None:
        """Update the status of a task result."""
        ...

    def set_conversation_id(self, result_id: str, conversation_id: str) -> None:
        """Set the conversation ID for a task result."""
        ...

    def set_file_outputs(self, result_id: str, file_outputs: list[str]) -> None:
        """Set the file output paths for a task result."""
        ...

    def get_completed_results_for_tasks(
        self, run_id: str, task_ids: list[str]
    ) -> list[tuple[str, str]]:
        """Returns (task.description, result_text) for completed deps in a run."""
        ...

    def get_due_recurring_goals(self) -> list[Goal]:
        """Active goals with cron, no in-progress run, and cron due since last run."""
        ...

    def reset_stale_running(self) -> None:
        """Reset task_results stuck in 'running' back to 'pending'."""
        ...


__all__ = ["TaskStore"]
