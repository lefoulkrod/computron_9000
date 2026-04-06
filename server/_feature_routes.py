"""HTTP route handlers for feature flags."""

from aiohttp import web

from config import load_config


async def handle_features(_request: web.Request) -> web.Response:
    """Return enabled feature flags for the UI."""
    features = load_config().features
    return web.json_response({
        "image_generation": features.image_generation,
        "music_generation": features.music_generation,
        "desktop": features.desktop,
        "visual_grounding": features.visual_grounding,
    })


def register_feature_routes(app: web.Application) -> None:
    """Register feature flag routes on the application."""
    app.router.add_route("GET", "/api/features", handle_features)


__all__ = ["register_feature_routes"]
