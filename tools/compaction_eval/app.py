"""Standalone compaction evaluation web app.

Run with: PYTHONPATH=. uv run python -m tools.compaction_eval.app
"""

from __future__ import annotations

import os
from pathlib import Path

from aiohttp import web

from sdk.providers._ollama import OllamaProvider

from ._routes import register_routes

_STATIC_DIR = Path(__file__).parent / "static"
_DEFAULT_PORT = 8081


def create_app() -> web.Application:
    """Create the aiohttp application."""
    app = web.Application()

    # Ollama provider
    host = os.environ.get("LLM_HOST", "http://localhost:11434")
    app["provider"] = OllamaProvider(host=host)

    # API routes
    register_routes(app)

    # Static files and index fallback
    app.router.add_get("/", _index_handler)
    app.router.add_static("/static/", _STATIC_DIR, name="static")

    return app


async def _index_handler(_request: web.Request) -> web.FileResponse:
    return web.FileResponse(_STATIC_DIR / "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", _DEFAULT_PORT))
    web.run_app(create_app(), port=port)
