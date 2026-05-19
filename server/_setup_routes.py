"""HTTP route handlers for the setup-completion API.

The setup wizard's finish step is a single server-side orchestration
instead of a chain of client-side calls. The client sends the user's
picks (provider, main model, optional vision model); this handler seeds
the per-use settings, stamps the shipped profiles, and flips
``setup_complete`` last — so a partial failure doesn't leave the app in
an incomplete-but-flagged-complete state.
"""

from __future__ import annotations

import json
import logging

from aiohttp import web
from pydantic import BaseModel, ConfigDict, ValidationError

from agents import apply_llm_config_to_profiles
from sdk.providers import get_provider
from settings import save_settings
from setup import mark_ready

logger = logging.getLogger(__name__)


class _CompleteBody(BaseModel):
    """Schema for ``POST /api/setup/complete``."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    main_model: str
    vision_model: str | None = None
    context_window: int | None = None
    default_agent: str = "computron"


async def handle_complete(request: web.Request) -> web.Response:
    """Finish the setup wizard server-side.

    Steps, in order so any failure short of the final flag-flip leaves
    a recoverable state:

    1. Validate the provider is actually configured (raises if not).
    2. Seed ``vision_provider`` / ``vision_model`` / ``compaction_provider``
       / ``compaction_model`` / ``title_provider`` / ``title_model`` and
       ``default_agent`` in settings.
    3. Stamp the shipped profiles with the chosen provider+model via
       ``apply_llm_config_to_profiles``.
    4. Flip ``setup_complete`` to true (last) and call ``mark_ready`` so
       any ready-gated waiters fire.
    """
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.json_response({"error": "invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"error": "request body must be a JSON object"}, status=400)
    try:
        spec = _CompleteBody(**body)
    except ValidationError as exc:
        logger.warning("invalid /api/setup/complete body: %s", exc)
        return web.json_response({"error": "Unknown or invalid field"}, status=400)

    try:
        get_provider(spec.provider)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)

    save_settings({
        "default_agent": spec.default_agent,
        # Vision is optional — if the wizard skipped, leave the per-use
        # fields empty so vision_generate returns its "no model configured"
        # error rather than half-resolving.
        "vision_provider": spec.provider if spec.vision_model else "",
        "vision_model": spec.vision_model or "",
        "compaction_provider": spec.provider,
        "compaction_model": spec.main_model,
        "title_provider": spec.provider,
        "title_model": spec.main_model,
    })

    apply_llm_config_to_profiles(
        spec.main_model,
        provider=spec.provider,
        context_window=spec.context_window,
    )

    saved = save_settings({"setup_complete": True})
    mark_ready(request.app)
    return web.json_response(saved)


def register_setup_routes(app: web.Application) -> None:
    """Register setup API routes."""
    app.router.add_route("POST", "/api/setup/complete", handle_complete)
