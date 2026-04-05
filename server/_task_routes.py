"""HTTP route handlers for the task engine API."""

from __future__ import annotations

import logging

from aiohttp import web

from conversations import delete_conversation
from tasks import get_store

logger = logging.getLogger(__name__)


def _cleanup_conversations(conv_ids: list[str]) -> None:
    """Delete conversation records for removed goals/runs."""
    for cid in conv_ids:
        delete_conversation(cid)


def _serialize_run(store, run) -> dict:
    """Serialize a run with its task_results for JSON responses."""
    results = store.get_task_results(run.id)
    return {**run.model_dump(), "task_results": [tr.model_dump() for tr in results]}


async def handle_list_goals(request: web.Request) -> web.Response:
    """List goals, optionally filtered by status."""
    status = request.query.get("status")
    store = get_store()
    goals = store.list_goals(status=status)
    result = []
    for g in goals:
        data = g.model_dump()
        runs = store.get_goal_runs(g.id)
        if runs:
            latest = max(runs, key=lambda r: r.started_at or r.created_at)
            data["last_run_at"] = latest.started_at or latest.created_at
        result.append(data)
    return web.json_response({"goals": result})


async def handle_get_goal(request: web.Request) -> web.Response:
    """Get full goal detail including tasks and runs with task_results."""
    goal_id = request.match_info["goal_id"]
    store = get_store()
    goal = store.get_goal(goal_id)
    if not goal:
        return web.json_response({"error": "Not found"}, status=404)
    tasks = store.list_tasks(goal_id)
    runs = store.get_goal_runs(goal_id)
    return web.json_response({
        "goal": goal.model_dump(),
        "tasks": [t.model_dump() for t in tasks],
        "runs": [_serialize_run(store, r) for r in runs],
    })


async def handle_delete_goal(request: web.Request) -> web.Response:
    """Delete a goal and all its runs/conversations."""
    goal_id = request.match_info["goal_id"]
    _cleanup_conversations(get_store().delete_goal(goal_id))
    return web.json_response({"deleted": goal_id})


async def handle_pause_goal(request: web.Request) -> web.Response:
    """Pause a goal — its tasks won't be picked up by the runner."""
    goal_id = request.match_info["goal_id"]
    get_store().set_goal_status(goal_id, "paused")
    return web.json_response({"status": "paused"})


async def handle_resume_goal(request: web.Request) -> web.Response:
    """Resume a paused goal."""
    goal_id = request.match_info["goal_id"]
    get_store().set_goal_status(goal_id, "active")
    return web.json_response({"status": "active"})


async def handle_trigger_goal(request: web.Request) -> web.Response:
    """Manually trigger a run for any goal (one-shot or recurring)."""
    goal_id = request.match_info["goal_id"]
    store = get_store()
    goal = store.get_goal(goal_id)
    if not goal:
        return web.json_response({"error": "Not found"}, status=404)
    run = store.queue_run(goal_id)
    return web.json_response({"run_id": run.id, "run_number": run.run_number}, status=201)


async def handle_list_runs(request: web.Request) -> web.Response:
    """List runs for a goal with their task_results."""
    goal_id = request.match_info["goal_id"]
    store = get_store()
    runs = store.get_goal_runs(goal_id)
    return web.json_response({"runs": [_serialize_run(store, r) for r in runs]})


async def handle_delete_run(request: web.Request) -> web.Response:
    """Delete a run and its conversations."""
    run_id = request.match_info["run_id"]
    _cleanup_conversations(get_store().delete_run(run_id))
    return web.json_response({"deleted": run_id})


async def handle_runner_status(request: web.Request) -> web.Response:
    """Return the current runner status."""
    runner = request.app.get("task_runner")
    if not runner:
        return web.json_response({
            "running": False,
            "paused": False,
            "active_tasks": 0,
            "max_concurrent": 0,
        })
    return web.json_response(runner.status)


async def handle_runner_pause(request: web.Request) -> web.Response:
    """Pause the task runner."""
    runner = request.app.get("task_runner")
    if runner:
        runner.pause()
    return web.json_response({"paused": True})


async def handle_runner_resume(request: web.Request) -> web.Response:
    """Resume the task runner."""
    runner = request.app.get("task_runner")
    if runner:
        runner.resume()
    return web.json_response({"paused": False})


def register_task_routes(app: web.Application) -> None:
    """Register all task engine HTTP routes on the application."""
    app.router.add_route("GET", "/api/goals", handle_list_goals)
    app.router.add_route("GET", "/api/goals/{goal_id}", handle_get_goal)
    app.router.add_route("DELETE", "/api/goals/{goal_id}", handle_delete_goal)
    app.router.add_route("POST", "/api/goals/{goal_id}/pause", handle_pause_goal)
    app.router.add_route("POST", "/api/goals/{goal_id}/resume", handle_resume_goal)
    app.router.add_route("POST", "/api/goals/{goal_id}/trigger", handle_trigger_goal)
    app.router.add_route("GET", "/api/goals/{goal_id}/runs", handle_list_runs)
    app.router.add_route("DELETE", "/api/goals/{goal_id}/runs/{run_id}", handle_delete_run)
    app.router.add_route("GET", "/api/runner/status", handle_runner_status)
    app.router.add_route("POST", "/api/runner/pause", handle_runner_pause)
    app.router.add_route("POST", "/api/runner/resume", handle_runner_resume)


__all__ = ["register_task_routes"]
