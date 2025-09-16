"""Entry point for starting the aiohttp chat server."""

# Third-party imports
import aiohttp.web
from dotenv import load_dotenv

# Local imports
from logging_config import setup_logging

# Load environment variables from .env before importing modules that may use them
load_dotenv()
setup_logging()

# Import the app after env and logging are set up
from server.aiohttp_app import app  # noqa: E402  (import after settings initialization)
from tools.browser.core.browser import close_browser  # noqa: E402
from utils.shutdown import register_shutdown_callback, run_shutdown_callbacks  # noqa: E402

PORT = 8080

if __name__ == "__main__":
    # Register shutdown callbacks and aiohttp shutdown hook in the entrypoint
    register_shutdown_callback(close_browser)
    # aiohttp on_shutdown callbacks receive the app arg; wrap our runner
    async def _run_shutdown_callbacks(_app: aiohttp.web.Application) -> None:  # type: ignore[name-defined]
        await run_shutdown_callbacks()

    app.on_shutdown.append(_run_shutdown_callbacks)
    aiohttp.web.run_app(app, port=PORT)
