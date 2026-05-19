"""HTTP route handlers for the models API."""

from __future__ import annotations

import logging
import re

from aiohttp import web

from sdk.providers import Provider, get_provider

logger = logging.getLogger(__name__)

# Patterns that could contain credentials; replaced before the message leaves the process.
_KEY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-[A-Za-z0-9_-]{10,}"), "sk-***"),
    (re.compile(r"Bearer\s+\S+", re.IGNORECASE), "Bearer ***"),
]


def _sanitize(msg: str) -> str:
    for pattern, replacement in _KEY_PATTERNS:
        msg = pattern.sub(replacement, msg)
    return msg


def _resolve_provider(request: web.Request) -> tuple[Provider | None, web.Response | None]:
    """Resolve the ``?provider=`` query to a provider, or build an error response.

    Exactly one of the two return values is non-None.
    """
    name = request.query.get("provider")
    if not name:
        return None, web.json_response({"error": "provider query parameter is required"}, status=400)
    try:
        return get_provider(name), None
    except ValueError as exc:
        return None, web.json_response({"error": _sanitize(str(exc))}, status=400)


async def handle_list_models(request: web.Request) -> web.Response:
    """Return available models with metadata for ``?provider=X``.

    400 if the provider is missing or unknown; 503 with a structured error
    if it's configured but unreachable, so the setup wizard / Providers page
    can show a clear message instead of a silent empty list.
    """
    provider, err = _resolve_provider(request)
    if err is not None:
        return err
    provider_name = request.query["provider"]
    try:
        models = await provider.list_models()
    except Exception as exc:  # noqa: BLE001 - any failure means "couldn't reach the provider"
        safe_msg = _sanitize(str(exc))
        logger.warning("Provider %s error listing models: %s", provider_name, safe_msg)
        return web.json_response(
            {"error": "provider_unreachable", "message": safe_msg, "provider": provider_name},
            status=503,
        )
    return web.json_response({"models": [m.model_dump() for m in models]})


async def handle_refresh_models(request: web.Request) -> web.Response:
    """Invalidate the cached model list for ``?provider=X`` so the next fetch re-queries it."""
    provider, err = _resolve_provider(request)
    if err is not None:
        return err
    provider.invalidate_model_cache()
    return web.json_response({"ok": True})


def register_model_routes(app: web.Application) -> None:
    """Register model API routes."""
    app.router.add_route("GET", "/api/models", handle_list_models)
    app.router.add_route("POST", "/api/models/refresh", handle_refresh_models)
