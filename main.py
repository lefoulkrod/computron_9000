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

PORT = 8080

if __name__ == "__main__":
    aiohttp.web.run_app(app, port=PORT)
