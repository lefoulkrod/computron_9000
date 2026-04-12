"""HTTP route handlers for the models API."""

from __future__ import annotations

import logging

from aiohttp import web

from config import load_config
from sdk.providers import get_provider

logger = logging.getLogger(__name__)


def _llm_host() -> str:
    """Return the configured LLM host for display in error responses."""
    cfg = load_config()
    return cfg.llm.host or "http://localhost:11434"


async def handle_list_models(request: web.Request) -> web.Response:
    """Return available models with metadata from the provider.

    Supports ``?capability=vision`` to filter by capability.

    Returns 503 with a structured error if the provider (e.g. Ollama) is
    unreachable, so the setup wizard can display a clear message instead of
    a silent empty list.
    """
    provider = get_provider()
    try:
        models = await provider.list_models_detailed()
    except Exception as exc:  # noqa: BLE001 - surface any provider error as 503
        logger.warning("Failed to list models from provider: %s", exc)
        return web.json_response(
            {
                "error": "provider_unreachable",
                "message": str(exc),
                "llm_host": _llm_host(),
            },
            status=503,
        )
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
