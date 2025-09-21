# Standard library imports
"""aiohttp web server exposing the COMPUTRON_9000 agent API.

This module now exposes a create_app() factory instead of instantiating the
application at import time. It also separates route handlers, uses Pydantic
models for structured validation, centralizes streaming logic, and configures
static file serving through aiohttp's built-in static route helpers.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web
from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import AsyncIterator, Awaitable, Callable

    from aiohttp.web_request import Request
    from aiohttp.web_response import Response, StreamResponse

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from collections.abc import Awaitable, Callable

from agents import handle_user_message, reset_message_history
from agents.types import Data

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
UI_DIST_DIR = Path(__file__).parent / "ui" / "dist"

# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------


class Attachment(BaseModel):
    """Represents a single attachment sent with a chat request."""

    base64: str
    content_type: str


class ChatRequest(BaseModel):
    """Request model for chat API with optional attachments."""

    message: str
    data: list[Attachment] | None = None


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS, GET, DELETE",
    "Access-Control-Allow-Headers": "Content-Type",
}


@web.middleware
async def cors_and_error_middleware(
    request: Request, handler: Callable[[Request], Awaitable[StreamResponse]]
) -> StreamResponse:
    """Add CORS headers and convert validation errors to JSON responses."""
    if request.method == "OPTIONS":
        return web.Response(status=200, headers=_CORS_HEADERS)
    try:
        resp: StreamResponse = await handler(request)
    except ValidationError as exc:  # pragma: no cover - handled uniformly
        logger.warning("Validation error: %s", exc)
        return web.json_response({"error": "Invalid request"}, status=400, headers=_CORS_HEADERS)
    if isinstance(resp, web.StreamResponse):
        for k, v in _CORS_HEADERS.items():
            resp.headers.setdefault(k, v)
    return resp


# ---------------------------------------------------------------------------
# Streaming helper
# ---------------------------------------------------------------------------


async def stream_events(
    request: Request,
    events: AsyncIterator[object],  # iterator of objects with message, final, thinking
) -> StreamResponse:
    """Stream JSONL events to the client.

    Args:
        request: Incoming aiohttp request.
        events: Async iterator of event objects with attributes message, final, thinking.

    Returns:
        StreamResponse prepared and fully written (EOF sent).
    """
    resp = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Transfer-Encoding": "chunked",
        },
    )
    await resp.prepare(request)
    try:
        async for event in events:
            data_out = {
                "response": getattr(event, "message", None),
                "final": getattr(event, "final", False),
                "thinking": getattr(event, "thinking", None),
            }
            await resp.write((json.dumps(data_out) + "\n").encode("utf-8"))
            if data_out.get("final"):
                break
    except Exception:  # pragma: no cover - defensive logging
        logger.exception("Error while streaming events")
        error_data = {"error": "Server error", "final": True}
        await resp.write((json.dumps(error_data) + "\n").encode("utf-8"))
    finally:
        await resp.write_eof()
    return resp


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def chat_handler(request: Request) -> StreamResponse:
    """Process chat messages and stream incremental model output."""
    raw_body = await request.text()
    try:
        payload = ChatRequest.model_validate_json(raw_body)
    except ValidationError as ve:
        logger.warning("Invalid chat request: %s", ve)
        raise
    user_query = payload.message.strip()
    if not user_query:
        return web.json_response({"error": "Message field is required."}, status=400)
    data_objs: list[Data] | None = None
    if payload.data:
        data_objs = [
            Data(base64_encoded=a.base64, content_type=a.content_type) for a in payload.data
        ]
    return await stream_events(request, handle_user_message(user_query, data_objs))


async def index_handler(_request: Request) -> StreamResponse:
    """Serve the main UI index file."""
    index_path = UI_DIST_DIR / "index.html"
    if not index_path.is_file():
        logger.warning("UI index not found: %s", index_path)
        return web.Response(text="<h1>File not found</h1>", content_type="text/html", status=404)
    return web.FileResponse(index_path)


async def delete_history_handler(_request: Request) -> Response:
    """Clear chat history."""
    reset_message_history()
    return web.Response(status=204)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app(*, client_max_size: int = 10 * 1024**2) -> web.Application:
    """Create and configure the aiohttp application.

    Args:
        client_max_size: Maximum allowed request body size in bytes.

    Returns:
        Configured aiohttp web.Application instance.
    """
    app = web.Application(client_max_size=client_max_size, middlewares=[cors_and_error_middleware])

    # API routes
    app.router.add_route("POST", "/api/chat", chat_handler)
    app.router.add_route("DELETE", "/api/chat/history", delete_history_handler)

    # UI routes
    app.router.add_route("GET", "/", index_handler)
    if UI_DIST_DIR.exists():
        app.router.add_static("/assets", UI_DIST_DIR / "assets", show_index=False)
    if STATIC_DIR.exists():
        app.router.add_static("/static", STATIC_DIR, show_index=False)
    return app


__all__ = ["create_app"]
