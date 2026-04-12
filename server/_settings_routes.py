"""HTTP route handlers for the application settings API."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from aiohttp import web

from config import load_config

logger = logging.getLogger(__name__)

_SETTINGS_FILE = "settings.json"


def _settings_path() -> Path:
    cfg = load_config()
    return Path(cfg.settings.home_dir) / _SETTINGS_FILE


def load_settings() -> dict[str, Any]:
    """Load settings from disk. Returns defaults if file doesn't exist."""
    path = _settings_path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            logger.warning("Failed to read settings file, using defaults")
    return {
        "setup_complete": False,
        "default_agent": "computron",
        "vision_model": "",
        "compaction_model": "",
    }


def save_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Merge data into settings and write to disk."""
    current = load_settings()
    current.update(data)
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2))
    return current


async def handle_get_settings(_request: web.Request) -> web.Response:
    """Return all application settings."""
    return web.json_response(load_settings())


async def handle_update_settings(request: web.Request) -> web.Response:
    """Update application settings (partial merge)."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.json_response({"error": "Invalid JSON"}, status=400)

    saved = save_settings(body)
    return web.json_response(saved)


def register_settings_routes(app: web.Application) -> None:
    """Register settings API routes."""
    app.router.add_route("GET", "/api/settings", handle_get_settings)
    app.router.add_route("PUT", "/api/settings", handle_update_settings)
