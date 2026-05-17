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


def _label(name: str) -> str:
    return _PROVIDER_LABELS.get(name, name)


async def handle_list_providers(_request: web.Request) -> web.Response:
    """Return configured LLM providers.

    Direct-connect providers (Ollama, no-auth OpenAI-compatible) come from
    ``settings.direct_providers``; brokered providers come from the
    integrations supervisor (singleton ``llm_<name>`` integrations).
    """
    settings = load_settings()

    providers: list[dict[str, object]] = []

    for name, entry in (settings.get("direct_providers") or {}).items():
        providers.append({
            "name": name,
            "label": _label(name),
            "kind": "direct",
            "base_url": entry.get("base_url"),
            "status": "configured",
        })

    integrations = await registered_integrations()
    for ri in integrations.values():
        if not ri.slug.startswith("llm_"):
            continue
        name = ri.slug.removeprefix("llm_")
        providers.append({
            "name": name,
            "label": _label(name),
            "kind": "brokered",
            "status": ri.state,
        })

    return web.json_response({"providers": providers})


def register_provider_routes(app: web.Application) -> None:
    """Register provider API routes."""
    app.router.add_route("GET", "/api/providers", handle_list_providers)
