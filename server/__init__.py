"""Server package for COMPUTRON_9000.

Exports the application factory `create_app` so callers can build their own
configured aiohttp application instance.
"""

from .aiohttp_app import create_app

__all__ = ["create_app"]
