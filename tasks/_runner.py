"""Background TaskRunner — asyncio loop that executes tasks autonomously."""

from __future__ import annotations

import asyncio
import logging
import traceback
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import GoalsConfig
    from tasks._executor import TaskExecutor
    from tasks._notifier import TelegramNotifier
    from tasks._store import TaskStore

logger = logging.getLogger(__name__)


class TaskRunner:
    """Background loop that polls for ready tasks and executes them.

    Runs as an asyncio task inside the aiohttp server process. Not a
    separate process — this keeps things simple and lets us reuse the
    existing event loop, providers, and browser contexts.
    """

    def __init__(
        self,
        store: TaskStore,
        executor: TaskExecutor,
        config: GoalsConfig,
        notifier: TelegramNotifier | None = None,
    ) -> None:
        self._store = store
        self._executor = executor
        self._config = config
        self._notifier = notifier
        self._running: dict[str, asyncio.Task] = {}  # task_result_id → asyncio.Task
        self._stop_event = asyncio.Event()
        self._paused = False
        self._loop_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the runner. Called from aiohttp on_startup."""
        self._store.reset_stale_running()
        self._loop_task = asyncio.create_task(self._poll_loop())
        logger.info("Task runner started")

    async def stop(self) -> None:
        """Stop the runner. Called from aiohttp on_cleanup."""
        self._stop_event.set()
        if self._loop_task:
            self._loop_task.cancel()
        if self._running:
            logger.info("Waiting for %d running tasks", len(self._running))
            await asyncio.wait(
                self._running.values(),
                timeout=self._config.shutdown_timeout,
            )

    def pause(self) -> None:
        """Pause the runner — stop picking up new tasks."""
        self._paused = True

    def resume(self) -> None:
        """Resume the runner."""
        self._paused = False

    @property
    def status(self) -> dict:
        """Return current runner status for the API."""
        return {
            "running": not self._paused and not self._stop_event.is_set(),
            "paused": self._paused,
            "active_tasks": len(self._running),
            "max_concurrent": self._config.max_concurrent,
        }

    async def _poll_loop(self) -> None:
        """Main loop — poll for work on each tick."""
        while not self._stop_event.is_set():
            if not self._paused:
                try:
                    await self._tick()
                except Exception:
                    logger.exception("Error in runner tick")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._config.poll_interval,
                )
                break  # stop_event was set
            except asyncio.TimeoutError:
                pass  # Normal — just means the poll interval elapsed

    async def _tick(self) -> None:
        """Single tick: spawn due runs, pick up ready tasks, clean up finished."""
        for goal in self._store.get_due_recurring_goals():
            run = self._store.spawn_run(goal.id)
            self._store.stamp_last_run_spawned(goal.id)
            logger.info("Spawned run #%d for goal %s", run.run_number, goal.id)

        for task_result, task in self._store.get_ready_task_results():
            if len(self._running) >= self._config.max_concurrent:
                break
            if task_result.id not in self._running:
                self._store.mark_task_result_running(task_result.id)
                self._store.update_run_status(task_result.run_id)
                self._running[task_result.id] = asyncio.create_task(
                    self._execute(task_result, task)
                )

        done = [trid for trid, t in self._running.items() if t.done()]
        for trid in done:
            del self._running[trid]

    async def _execute(self, task_result: "TaskResult", task: "Task") -> None:
        """Execute a task result with retry on failure.

        On retriable failure, sets the result back to pending and records
        a ``retry_after`` timestamp. The slot is freed immediately — the
        tick loop will re-pick it up once the backoff has elapsed (checked
        via ``retry_count`` and poll timing).
        """
        try:
            result_text, file_paths = await self._executor.run(task_result, task)
            if file_paths:
                self._store.set_file_outputs(task_result.id, file_paths)
            self._store.mark_task_result_completed(task_result.id, result_text)
        except Exception:
            error_msg = traceback.format_exc()
            logger.exception("TaskResult %s failed", task_result.id)

            if task_result.retry_count < task.max_retries:
                delay = self._config.retry_backoff_base * (
                    2 ** task_result.retry_count
                )
                self._store.increment_retry(task_result.id, error_msg)
                self._store.update_task_result_status(task_result.id, "pending")
                logger.info(
                    "TaskResult %s set to pending for retry (%d/%d, backoff %ds)",
                    task_result.id,
                    task_result.retry_count + 1,
                    task.max_retries,
                    delay,
                )
            else:
                self._store.mark_task_result_failed(task_result.id, error_msg)

        new_status = self._store.update_run_status(task_result.run_id)
        if new_status in ("completed", "failed") and self._notifier:
            await self._notify_run_finished(task_result.run_id, new_status)

    async def _notify_run_finished(self, run_id: str, status: str) -> None:
        """Send a Telegram notification when a run reaches a terminal state."""
        from pathlib import Path

        from tasks._notifier import format_run_completed, format_run_failed

        cfg = self._config.notifications
        if status == "completed" and not cfg.on_run_completed:
            return
        if status == "failed" and not cfg.on_run_failed:
            return

        run = self._store.get_run(run_id)
        if not run:
            return
        goal = self._store.get_goal(run.goal_id)
        if not goal:
            return

        results = self._store.get_task_results(run_id)
        tasks = {t.id: t for t in self._store.list_tasks(run.goal_id)}
        completed_count = sum(1 for r in results if r.status == "completed")
        total_count = len(results)

        duration = ""
        if run.started_at and run.completed_at:
            from datetime import datetime

            try:
                start = datetime.fromisoformat(run.started_at)
                end = datetime.fromisoformat(run.completed_at)
                secs = int((end - start).total_seconds())
                duration = f"{secs // 60}m {secs % 60}s" if secs >= 60 else f"{secs}s"
            except (ValueError, TypeError):
                duration = ""

        # Collect all file output paths from all task results
        all_files: list[Path] = []
        if cfg.include_files:
            for r in results:
                for fp in r.file_outputs:
                    p = Path(fp)
                    if p.is_file():
                        all_files.append(p)

        if status == "completed":
            # Use the last completed task's result as the final output
            last_result = ""
            for r in reversed(results):
                if r.status == "completed" and r.result:
                    last_result = r.result
                    break
            message = format_run_completed(
                goal_description=goal.description,
                run_number=run.run_number,
                duration=duration,
                total_tasks=total_count,
                completed_tasks=completed_count,
                final_output=last_result,
                file_count=len(all_files),
            )
        else:
            # Find the failed task
            failed_desc = "unknown"
            error = ""
            for r in results:
                if r.status == "failed":
                    task = tasks.get(r.task_id)
                    failed_desc = task.description if task else r.task_id
                    error = r.error or ""
                    break
            message = format_run_failed(
                goal_description=goal.description,
                run_number=run.run_number,
                duration=duration,
                total_tasks=total_count,
                completed_tasks=completed_count,
                failed_task_description=failed_desc,
                error=error,
            )

        assert self._notifier is not None  # Guarded by caller
        await self._notifier.send(message, all_files if all_files else None)


__all__ = ["TaskRunner"]
