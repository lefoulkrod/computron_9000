"""Entry point for starting the aiohttp chat server."""

from __future__ import annotations

import logging
import os

import aiohttp.web
from dotenv import load_dotenv

from logging_config import setup_logging
from server.aiohttp_app import create_app
from tools.browser.core.browser import close_browser

logger = logging.getLogger(__name__)

PORT = int(os.getenv("PORT", "8080"))


async def initialize_services(_app: aiohttp.web.Application) -> None:
    """Initialize all services including MCP."""
    from tools.mcp import get_mcp_registry

    registry = get_mcp_registry()
    await registry.initialize()


async def shutdown_services(_app: aiohttp.web.Application) -> None:
    """Shutdown all services including MCP."""
    from tools.mcp import get_mcp_registry

    registry = get_mcp_registry()
    await registry.shutdown()


def main() -> None:
    """Create and run the aiohttp application instance.

    Logging and environment variables are initialized here (runtime boundary)
    rather than at import time so that importing this module in tests or other
    tooling does not produce side effects.
    """
    # Initialize environment and logging only when actually running the server.
    load_dotenv()
    setup_logging()
    app = create_app()

    async def _close_browser(_app: aiohttp.web.Application) -> None:  # pragma: no cover
        await close_browser()

    async def _shutdown_executor(_app: aiohttp.web.Application) -> None:  # pragma: no cover
        import asyncio
        loop = asyncio.get_running_loop()
        try:
            await asyncio.wait_for(loop.shutdown_default_executor(), timeout=5.0)
        except asyncio.TimeoutError:
            # Some thread (e.g. a Docker exec stream) is stuck on blocking I/O.
            # Python's _python_exit atexit handler would join it indefinitely, so
            # force-quit now to avoid requiring multiple Ctrl+C presses.
            logger.warning("Executor threads did not finish within 5s; forcing exit")
            os._exit(0)

    app.on_startup.append(initialize_services)
    app.on_shutdown.append(shutdown_services)
    app.on_shutdown.append(_close_browser)
    app.on_cleanup.append(_shutdown_executor)
    logger.info("Starting server on port %s", PORT)
    aiohttp.web.run_app(app, port=PORT)


if __name__ == "__main__":  # pragma: no cover
    main()
