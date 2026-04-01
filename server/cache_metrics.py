"""Cache metrics endpoint for monitoring semantic cache performance."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiohttp import web

from utils.semantic_cache import get_metrics, clear_all_caches

if TYPE_CHECKING:
    from aiohttp.web_request import Request
    from aiohttp.web_response import Response

logger = logging.getLogger(__name__)


async def cache_metrics_handler(request: Request) -> Response:
    """Return cache metrics as JSON.

    Returns a JSON response with cache hit/miss metrics for all cached
    functions, including the number of hits, misses, and semantic hits.

    Args:
        request: The incoming HTTP request.

    Returns:
        JSON response with cache metrics.
    """
    metrics = get_metrics()
    return web.json_response(metrics)


async def cache_clear_handler(request: Request) -> Response:
    """Clear all caches (admin endpoint).

    Clears all semantic caches and returns a status response.

    Args:
        request: The incoming HTTP request.

    Returns:
        JSON response with status message.
    """
    clear_all_caches()
    logger.info("Cache cleared via API")
    return web.json_response({"status": "cleared"})


def setup_cache_routes(app: web.Application) -> None:
    """Add cache routes to aiohttp app.

    Registers the cache metrics and clear endpoints with the application.

    Args:
        app: The aiohttp application instance.
    """
    app.router.add_get("/api/cache/metrics", cache_metrics_handler)
    app.router.add_post("/api/cache/clear", cache_clear_handler)
    logger.debug("Cache routes registered")
