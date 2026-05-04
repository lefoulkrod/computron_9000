"""HTTP route handlers for the application settings API."""

from __future__ import annotations

import json
import logging

from aiohttp import web
from pydantic import ValidationError

from config import load_config
from sdk.providers import reset_provider
from settings import SettingsUpdate, load_settings, save_settings

logger = logging.getLogger(__name__)

# When any of these fields change, the provider singleton and config cache must
# be invalidated so the next request picks up the new connection details.
# llm_api_key is no longer in settings — keys live in the supervisor vault.
_LLM_FIELDS: frozenset[str] = frozenset({"llm_provider", "llm_base_url"})


async def handle_get_settings(_request: web.Request) -> web.Response:
    """Return all application settings."""
    return web.json_response(load_settings())


async def handle_update_settings(request: web.Request) -> web.Response:
    """Update application settings (partial merge)."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.json_response({"error": "Invalid JSON"}, status=400)

    if not isinstance(body, dict):
        return web.json_response({"error": "Request body must be a JSON object"}, status=400)

    try:
        update = SettingsUpdate(**body)
    except ValidationError as exc:
        logger.warning("Invalid settings update: %s", exc)
        return web.json_response({"error": "Unknown or invalid settings field"}, status=400)

    was_complete = load_settings().get("setup_complete", False)
    saved = save_settings(update.model_dump(exclude_unset=True))

    # If LLM connection settings changed, drop the cached provider so the next
    # request re-initialises it with the new config. Also clear load_config's
    # lru_cache in case env var resolution should be re-evaluated.
    if _LLM_FIELDS & update.model_fields_set:
        load_config.cache_clear()
        reset_provider()

    if not was_complete and saved.get("setup_complete"):
        from setup import mark_ready
        mark_ready(request.app)

    return web.json_response(saved)


def register_settings_routes(app: web.Application) -> None:
    """Register settings API routes."""
    app.router.add_route("GET", "/api/settings", handle_get_settings)
    app.router.add_route("PUT", "/api/settings", handle_update_settings)
