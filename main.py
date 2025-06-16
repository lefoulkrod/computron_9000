"""Entry point for starting the aiohttp chat server."""

from logging_config import setup_logging

setup_logging()

# Third-party imports
import aiohttp.web

from server.aiohttp_app import app

PORT = 8080

if __name__ == "__main__":
    aiohttp.web.run_app(app, port=PORT)
