"""HTTP route handlers for the agent profile API."""

from __future__ import annotations

import json
import logging

from aiohttp import web

from agents._agent_profiles import (
    AgentProfile,
    delete_agent_profile,
    duplicate_agent_profile,
    get_agent_profile,
    list_agent_profiles,
    save_agent_profile,
    set_model_on_profiles,
)

logger = logging.getLogger(__name__)


async def handle_list_profiles(request: web.Request) -> web.Response:
    """Return agent profiles.

    By default only enabled profiles are returned. Pass
    ``?include_disabled=true`` to include disabled profiles (used by the
    profile management UI).
    """
    include_disabled = request.query.get("include_disabled", "").lower() == "true"
    profiles = list_agent_profiles(include_disabled=include_disabled)
    return web.json_response([p.model_dump() for p in profiles])


async def handle_get_profile(request: web.Request) -> web.Response:
    """Return a single agent profile by ID."""
    profile_id = request.match_info["id"]
    profile = get_agent_profile(profile_id)
    if profile is None:
        return web.json_response({"error": f"Profile '{profile_id}' not found"}, status=404)
    return web.json_response(profile.model_dump())


async def handle_create_profile(request: web.Request) -> web.Response:
    """Create a new agent profile."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.json_response({"error": "Invalid JSON"}, status=400)
    try:
        profile = AgentProfile.model_validate(body)
        saved = save_agent_profile(profile)
        return web.json_response(saved.model_dump(), status=201)
    except Exception as exc:
        logger.warning("Failed to create profile: %s", exc)
        return web.json_response({"error": str(exc)}, status=400)


async def handle_update_profile(request: web.Request) -> web.Response:
    """Update an existing agent profile.

    Refuses to set ``enabled: false`` on the profile currently configured
    as the system-wide default agent — that would leave the system with
    no fallback. The caller must change the default first.
    """
    profile_id = request.match_info["id"]
    existing = get_agent_profile(profile_id)
    if existing is None:
        return web.json_response({"error": f"Profile '{profile_id}' not found"}, status=404)
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.json_response({"error": "Invalid JSON"}, status=400)

    # Block disabling the currently-set default agent.
    if body.get("enabled") is False:
        from settings import load_settings
        default_id = load_settings().get("default_agent")
        if default_id == profile_id:
            return web.json_response(
                {
                    "error": "default_agent_cannot_be_disabled",
                    "message": (
                        "This profile is currently set as the default agent. "
                        "Change the default in Settings → System before disabling it."
                    ),
                },
                status=400,
            )

    try:
        body["id"] = profile_id
        profile = AgentProfile.model_validate(body)
        saved = save_agent_profile(profile)
        return web.json_response(saved.model_dump())
    except Exception as exc:
        logger.warning("Failed to update profile '%s': %s", profile_id, exc)
        return web.json_response({"error": str(exc)}, status=400)


async def handle_delete_profile(request: web.Request) -> web.Response:
    """Delete an agent profile. Returns 409 if tasks reference it."""
    profile_id = request.match_info["id"]
    profile = get_agent_profile(profile_id)
    if profile is None:
        return web.json_response({"error": f"Profile '{profile_id}' not found"}, status=404)

    # Check for task usage
    usage = _get_profile_usage(profile_id)
    if usage:
        logger.warning(
            "Refused delete of profile '%s': in use by %d task(s)",
            profile_id, len(usage),
        )
        return web.json_response({
            "error": "Profile is in use by tasks",
            "usage": usage,
        }, status=409)

    try:
        delete_agent_profile(profile_id)
        return web.Response(status=204)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)


async def handle_duplicate_profile(request: web.Request) -> web.Response:
    """Duplicate an agent profile."""
    profile_id = request.match_info["id"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    new_name = body.get("name")
    try:
        clone = duplicate_agent_profile(profile_id, new_name)
        return web.json_response(clone.model_dump(), status=201)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=404)


async def handle_profile_usage(request: web.Request) -> web.Response:
    """Return goals/tasks that reference this profile."""
    profile_id = request.match_info["id"]
    if get_agent_profile(profile_id) is None:
        return web.json_response({"error": f"Profile '{profile_id}' not found"}, status=404)
    usage = _get_profile_usage(profile_id)
    return web.json_response({"usage": usage})


async def handle_set_model(request: web.Request) -> web.Response:
    """Set the model on all profiles that have no model. Used by setup wizard."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.json_response({"error": "Invalid JSON"}, status=400)
    model = body.get("model")
    if not model:
        return web.json_response({"error": "model is required"}, status=400)
    try:
        set_model_on_profiles(model)
        return web.json_response({"ok": True})
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500)


def _get_profile_usage(profile_id: str) -> list[dict]:
    """Find goals/tasks referencing a profile."""
    try:
        from tasks import get_store
        store = get_store()
    except RuntimeError:
        return []
    usage: list[dict] = []
    for goal in store.list_goals():
        tasks = store.list_tasks(goal.id)
        for task in tasks:
            if getattr(task, "agent_profile", None) == profile_id:
                usage.append({
                    "goal_id": goal.id,
                    "goal_description": goal.description,
                    "task_id": task.id,
                    "task_description": task.description,
                })
    return usage


async def handle_list_agents(_request: web.Request) -> web.Response:
    """Return agent profile IDs and the default agent."""
    from settings import load_settings
    profiles = list_agent_profiles()
    default_agent = load_settings().get("default_agent", "computron")
    return web.json_response({
        "agents": [p.id for p in profiles],
        "default": default_agent,
    })


def register_profile_routes(app: web.Application) -> None:
    """Register all profile API routes."""
    app.router.add_route("GET", "/api/agents", handle_list_agents)
    app.router.add_route("GET", "/api/profiles", handle_list_profiles)
    app.router.add_route("POST", "/api/profiles", handle_create_profile)
    app.router.add_route("POST", "/api/profiles/set-model", handle_set_model)
    app.router.add_route("GET", "/api/profiles/{id}", handle_get_profile)
    app.router.add_route("PUT", "/api/profiles/{id}", handle_update_profile)
    app.router.add_route("DELETE", "/api/profiles/{id}", handle_delete_profile)
    app.router.add_route("POST", "/api/profiles/{id}/duplicate", handle_duplicate_profile)
    app.router.add_route("GET", "/api/profiles/{id}/usage", handle_profile_usage)
