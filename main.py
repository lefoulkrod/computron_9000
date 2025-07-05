"""Entry point for starting the aiohttp chat server."""

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from logging_config import setup_logging

# Third-party imports
import aiohttp.web

from server.aiohttp_app import app

setup_logging()

PORT = 8080

if __name__ == "__main__":
    aiohttp.web.run_app(app, port=PORT)
