"""HTTP route handlers for the models API."""

from __future__ import annotations

from aiohttp import web

from sdk.providers import get_provider


async def handle_list_models(request: web.Request) -> web.Response:
    """Return available models with metadata from the provider.

    Supports ``?capability=vision`` to filter by capability.
    """
    provider = get_provider()
    models = await provider.list_models_detailed()
    capability = request.query.get("capability")
    if capability:
        models = [m for m in models if capability in m.get("capabilities", [])]
    return web.json_response({"models": models})


async def handle_refresh_models(_request: web.Request) -> web.Response:
    """Invalidate the cached model list so the next fetch re-queries Ollama."""
    provider = get_provider()
    provider.invalidate_model_cache()
    return web.json_response({"ok": True})


async def handle_list_agents(_request: web.Request) -> web.Response:
    """Return the list of available agent profiles."""
    from agents._agent_profiles import list_agent_profiles
    profiles = list_agent_profiles()
    return web.json_response({
        "agents": [p.id for p in profiles],
        "default": "computron",
    })


def register_model_routes(app: web.Application) -> None:
    """Register model API routes."""
    app.router.add_route("GET", "/api/models", handle_list_models)
    app.router.add_route("POST", "/api/models/refresh", handle_refresh_models)
    app.router.add_route("GET", "/api/agents", handle_list_agents)
