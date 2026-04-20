"""HTTP route handlers for the models API."""

from __future__ import annotations

import logging

from aiohttp import web

from config import load_config
from sdk.providers import get_provider
from sdk.providers._models import ProviderError

logger = logging.getLogger(__name__)


def _llm_host() -> str:
    """Return the configured LLM host for display in error responses."""
    cfg = load_config()
    return cfg.llm.host or "http://localhost:11434"


async def handle_list_models(request: web.Request) -> web.Response:
    """Return available models with metadata from the provider.

    Supports ``?capability=vision`` to filter by capability.

    Returns 503 with a structured error if the provider is unreachable,
    so the setup wizard can display a clear message instead of a silent
    empty list.
    """
    provider = get_provider()
    try:
        models = await provider.list_models_detailed()
    except ProviderError as exc:
        # Log full error at DEBUG to avoid leaking API keys to app logs.
        logger.debug("Provider error listing models: %s", exc)
        safe_msg = f"Provider returned HTTP {exc.status_code}" if exc.status_code else "Provider is unreachable"
        return web.json_response(
            {
                "error": "provider_unreachable",
                "message": safe_msg,
                "llm_host": _llm_host(),
            },
            status=503,
        )
    except Exception as exc:
        logger.debug("Unexpected error listing models: %s", exc)
        return web.json_response(
            {
                "error": "provider_unreachable",
                "message": "Provider is unreachable",
                "llm_host": _llm_host(),
            },
            status=503,
        )
    capability = request.query.get("capability")
    if capability:
        models = [m for m in models if capability in m.get("capabilities", [])]
    return web.json_response({"models": models})


async def handle_refresh_models(_request: web.Request) -> web.Response:
    """Invalidate the cached model list so the next fetch re-queries the provider."""
    provider = get_provider()
    provider.invalidate_model_cache()
    return web.json_response({"ok": True})


def register_model_routes(app: web.Application) -> None:
    """Register model API routes."""
    app.router.add_route("GET", "/api/models", handle_list_models)
    app.router.add_route("POST", "/api/models/refresh", handle_refresh_models)
