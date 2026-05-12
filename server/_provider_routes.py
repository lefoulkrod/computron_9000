"""HTTP route handlers for the providers API."""

from __future__ import annotations

import logging

from aiohttp import web

from settings import load_settings
from tools.integrations import registered_integrations

logger = logging.getLogger(__name__)

_PROVIDER_LABELS: dict[str, str] = {
    "ollama": "Ollama",
    "openai": "OpenAI API",
    "anthropic": "Anthropic API",
    "openrouter": "OpenRouter",
    "openai_compat": "OpenAI-compatible",
}


async def handle_list_providers(_request: web.Request) -> web.Response:
    """Return configured LLM providers and their status.

    Ollama is always included (it connects directly, no broker needed).
    Cloud providers are discovered from the integrations supervisor cache.
    """
    settings = load_settings()
    default_provider = settings.get("llm_provider", "ollama")

    providers = []

    # Ollama is always available as a direct-connect provider
    providers.append({
        "name": "ollama",
        "label": _PROVIDER_LABELS["ollama"],
        "status": "connected",
        "is_default": default_provider == "ollama",
    })

    # Cloud providers come from the integrations supervisor
    integrations = await registered_integrations()
    for integration in integrations.values():
        if not integration.slug.startswith("llm_"):
            continue
        # "llm_anthropic" → "anthropic"
        name = integration.slug.removeprefix("llm_")
        providers.append({
            "name": name,
            "label": _PROVIDER_LABELS.get(name, name),
            "status": integration.state,
            "is_default": default_provider == name,
        })

    return web.json_response({
        "providers": providers,
        "default_provider": default_provider,
    })


def register_provider_routes(app: web.Application) -> None:
    """Register provider API routes."""
    app.router.add_route("GET", "/api/providers", handle_list_providers)
