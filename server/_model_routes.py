"""HTTP route handlers for the models API."""

from __future__ import annotations

import logging
import re

from aiohttp import web

from config import load_config
from sdk.providers import get_provider
from sdk.providers._models import ProviderError

logger = logging.getLogger(__name__)

# Patterns that could contain credentials; replaced before the message leaves the process.
_KEY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-[A-Za-z0-9_-]{10,}"), "sk-***"),
    (re.compile(r"Bearer\s+\S+", re.IGNORECASE), "Bearer ***"),
]


def _sanitize(msg: str, api_key: str | None = None) -> str:
    for pattern, replacement in _KEY_PATTERNS:
        msg = pattern.sub(replacement, msg)
    if api_key:
        msg = msg.replace(api_key, "***")
    return msg


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
        cfg = load_config()
        safe_msg = _sanitize(str(exc), cfg.llm.api_key)
        logger.warning("Provider error listing models: %s", safe_msg)
        return web.json_response(
            {
                "error": "provider_unreachable",
                "message": safe_msg,
                "llm_host": cfg.llm.host or "http://localhost:11434",
            },
            status=503,
        )
    except Exception as exc:
        cfg = load_config()
        safe_msg = _sanitize(str(exc), cfg.llm.api_key)
        logger.warning("Unexpected error listing models: %s", safe_msg)
        return web.json_response(
            {
                "error": "provider_unreachable",
                "message": safe_msg,
                "llm_host": cfg.llm.host or "http://localhost:11434",
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
