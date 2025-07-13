"""Entry point for starting the aiohttp chat server."""

# Standard library imports
# Third-party imports
import aiohttp.web
from dotenv import load_dotenv

# Local imports
from logging_config import setup_logging
from server.aiohttp_app import app

# Load environment variables from .env file
load_dotenv()
setup_logging()

PORT = 8080

if __name__ == "__main__":
    aiohttp.web.run_app(app, port=PORT)
