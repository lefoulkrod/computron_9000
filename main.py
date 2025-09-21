"""Entry point for starting the aiohttp chat server."""

from __future__ import annotations

import logging
import os

import aiohttp.web
from dotenv import load_dotenv

from logging_config import setup_logging
from server.aiohttp_app import create_app
from tools.browser.core.browser import close_browser
from utils.shutdown import register_shutdown_callback, run_shutdown_callbacks

load_dotenv()
setup_logging()
logger = logging.getLogger(__name__)

PORT = int(os.getenv("PORT", "8080"))


def main() -> None:
    """Create and run the aiohttp application instance."""
    app = create_app()
    register_shutdown_callback(close_browser)

    async def _run_shutdown_callbacks(_app: aiohttp.web.Application) -> None:  # pragma: no cover
        await run_shutdown_callbacks()

    app.on_shutdown.append(_run_shutdown_callbacks)
    logger.info("Starting server on port %s", PORT)
    aiohttp.web.run_app(app, port=PORT)


if __name__ == "__main__":  # pragma: no cover
    main()
