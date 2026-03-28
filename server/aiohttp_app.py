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

import asyncio

from server.message_handler import AVAILABLE_AGENTS, handle_user_message, reset_message_history, resume_conversation
from sdk.providers import get_provider
from sdk.turn import is_turn_active, queue_nudge, request_stop
from agents.types import Data, LLMOptions
from config import load_config
from tools.custom_tools.registry import delete_tool, list_tools
from tools.memory import forget as forget_memory
from tools.memory import load_memory, set_key_hidden
from conversations._store import (
    delete_conversation as _delete_conversation,
    delete_turn as _delete_turn,
    list_conversations as _list_conversations,
    list_turns as _list_turns,
    load_turn as _load_turn,
)
from tools.desktop._lifecycle import is_desktop_running, start_desktop
from tools.desktop._exec import DesktopExecError

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
    filename: str | None = None


class ChatRequest(BaseModel):
    """Request model for chat API with optional attachments."""

    message: str
    data: list[Attachment] | None = None
    options: LLMOptions | None = None
    conversation_id: str | None = None
    agent: str | None = None


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


if TYPE_CHECKING:  # pragma: no cover - typing only
    from sdk.events import AgentEvent


async def stream_events(
    request: Request,
    events: AsyncIterator[AgentEvent],  # iterator of AgentEvent
) -> StreamResponse:
    """Stream JSONL events to the client.

    Args:
        request: Incoming aiohttp request.
        events: Async iterator yielding `AgentEvent` instances produced by
            `handle_user_message`.

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
            data_out = event.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
            await resp.write((json.dumps(data_out) + "\n").encode("utf-8"))
    except ConnectionResetError:
        logger.debug("Client disconnected during event stream")
    except Exception:  # pragma: no cover - defensive logging
        logger.exception("Error while streaming events")
        try:
            error_data = {"error": "Server error", "payload": {"type": "turn_end"}}
            await resp.write((json.dumps(error_data) + "\n").encode("utf-8"))
        except ConnectionResetError:
            pass
    finally:
        try:
            await resp.write_eof()
        except ConnectionResetError:
            pass
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

    # If this conversation already has an active agent, queue the message as a nudge
    if is_turn_active(payload.conversation_id):
        queue_nudge(payload.conversation_id or "default", user_query)
        return web.json_response({"ok": True})

    data_objs: list[Data] | None = None
    if payload.data:
        data_objs = [
            Data(base64_encoded=a.base64, content_type=a.content_type, filename=a.filename)
            for a in payload.data
        ]
    return await stream_events(
        request,
        handle_user_message(
            user_query, data_objs, options=payload.options,
            conversation_id=payload.conversation_id, agent=payload.agent,
        ),
    )


async def container_file_handler(request: Request) -> StreamResponse:
    """Serve files from the container's home directory via the host volume mount."""
    path = request.match_info.get("path", "")
    cfg = load_config()
    host_home = Path(cfg.virtual_computer.home_dir).resolve()
    host_path = (host_home / path).resolve()

    if not host_path.is_relative_to(host_home):
        return web.Response(status=403, text="Forbidden")
    if not host_path.is_file():
        return web.Response(status=404, text="Not found")

    return web.FileResponse(host_path)


async def index_handler(_request: Request) -> StreamResponse:
    """Serve the main UI index file."""
    index_path = UI_DIST_DIR / "index.html"
    if not index_path.is_file():
        logger.warning("UI index not found: %s", index_path)
        return web.Response(text="<h1>File not found</h1>", content_type="text/html", status=404)
    return web.FileResponse(index_path)


async def stop_handler(request: Request) -> Response:
    """Interrupt the active agent conversation turn."""
    conversation_id = request.query.get("conversation_id")
    request_stop(conversation_id=conversation_id)
    return web.json_response({"ok": True})


async def delete_history_handler(request: Request) -> Response:
    """Clear chat history for a conversation."""
    conversation_id = request.query.get("conversation_id")
    reset_message_history(conversation_id=conversation_id)
    return web.Response(status=204)


async def list_custom_tools_handler(_request: Request) -> Response:
    """Return all custom tool definitions as JSON."""
    tools = list_tools()
    data = [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "type": t.type,
            "language": t.language,
            "tags": t.tags,
            "created_at": t.created_at,
        }
        for t in tools
    ]
    return web.json_response(data)


async def delete_custom_tool_handler(request: Request) -> Response:
    """Delete a custom tool by name."""
    name = request.match_info["name"]
    found = delete_tool(name)
    if not found:
        return web.json_response({"error": f"Tool '{name}' not found"}, status=404)
    return web.Response(status=204)


async def list_agents_handler(_request: Request) -> Response:
    """Return the list of available agent IDs."""
    return web.json_response({"agents": AVAILABLE_AGENTS, "default": "computron"})


async def list_models_handler(_request: Request) -> Response:
    """Return available models from the provider."""
    provider = get_provider()
    models = await provider.list_models()
    return web.json_response({
        "models": models,
    })


async def list_memory_handler(_request: Request) -> Response:
    """Return all stored memories and the set of hidden keys."""
    entries = load_memory()
    return web.json_response({
        "entries": {k: e.value for k, e in entries.items()},
        "hidden": sorted(k for k, e in entries.items() if e.hidden),
    })


async def delete_memory_handler(request: Request) -> Response:
    """Delete a memory entry by key."""
    key = request.match_info["key"]
    result = await forget_memory(key)
    if result.get("status") == "not_found":
        return web.json_response({"error": f"Memory key '{key}' not found"}, status=404)
    return web.Response(status=204)


async def list_turns_handler(request: Request) -> Response:
    """Return turn index entries (paginated)."""
    limit = int(request.query.get("limit", "50"))
    offset = int(request.query.get("offset", "0"))
    outcome = request.query.get("outcome")
    entries = _list_turns(limit=limit, offset=offset, outcome=outcome)
    data = [e.model_dump() for e in entries]
    return web.json_response(data)


async def get_turn_handler(request: Request) -> Response:
    """Return a full turn transcript."""
    turn_id = request.match_info["id"]
    record = _load_turn(turn_id)
    if record is None:
        return web.json_response({"error": "Turn not found"}, status=404)
    return web.json_response(record.model_dump())


async def delete_turn_handler(request: Request) -> Response:
    """Delete a turn by ID."""
    turn_id = request.match_info["id"]
    found = _delete_turn(turn_id)
    if not found:
        return web.json_response({"error": "Turn not found"}, status=404)
    return web.Response(status=204)


async def list_conversations_handler(_request: Request) -> Response:
    """Return past conversation summaries for the conversations panel."""
    summaries = _list_conversations()
    data = [s.model_dump() for s in summaries]
    return web.json_response(data)


async def delete_conversation_handler(request: Request) -> Response:
    """Delete a conversation and all its turns/history."""
    conversation_id = request.match_info["conversation_id"]
    found = _delete_conversation(conversation_id)
    if not found:
        return web.json_response({"error": "Conversation not found"}, status=404)
    return web.Response(status=204)


async def resume_conversation_handler(request: Request) -> Response:
    """Resume a past conversation by loading its full-fidelity history."""
    conversation_id = request.match_info["conversation_id"]
    messages = resume_conversation(conversation_id)
    if messages is None:
        return web.json_response({"error": "Conversation not found"}, status=404)
    return web.json_response({"conversation_id": conversation_id, "messages": messages})


async def set_memory_hidden_handler(request: Request) -> Response:
    """Set the hidden flag for a memory entry."""
    key = request.match_info["key"]
    if key not in load_memory():
        return web.json_response({"error": f"Memory key '{key}' not found"}, status=404)
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.json_response({"error": "Invalid JSON body"}, status=400)
    set_key_hidden(key, bool(body.get("hidden", False)))
    return web.Response(status=204)


async def desktop_start_handler(_request: Request) -> Response:
    """Start the desktop environment and return its status."""
    try:
        await start_desktop()
        return web.json_response({"running": True})
    except DesktopExecError as exc:
        return web.json_response(
            {"running": False, "error": str(exc)}, status=503,
        )


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
    app.router.add_route("POST", "/api/chat/stop", stop_handler)
    app.router.add_route("DELETE", "/api/chat/history", delete_history_handler)
    app.router.add_route("GET", "/api/agents", list_agents_handler)
    app.router.add_route("GET", "/api/models", list_models_handler)
    app.router.add_route("GET", "/api/custom-tools", list_custom_tools_handler)
    app.router.add_route("DELETE", "/api/custom-tools/{name}", delete_custom_tool_handler)
    app.router.add_route("GET", "/api/memory", list_memory_handler)
    app.router.add_route("DELETE", "/api/memory/{key}", delete_memory_handler)
    app.router.add_route("POST", "/api/memory/{key}/hidden", set_memory_hidden_handler)

    # Desktop API
    app.router.add_route("POST", "/api/desktop/start", desktop_start_handler)

    # Sessions API (conversation resume) — must be before {id} wildcard routes
    app.router.add_route("GET", "/api/conversations/sessions", list_conversations_handler)
    app.router.add_route("POST", "/api/conversations/sessions/{conversation_id}/resume", resume_conversation_handler)
    app.router.add_route("DELETE", "/api/conversations/sessions/{conversation_id}", delete_conversation_handler)

    # Turns API (formerly conversations)
    app.router.add_route("GET", "/api/conversations", list_turns_handler)
    app.router.add_route("GET", "/api/conversations/{id}", get_turn_handler)
    app.router.add_route("DELETE", "/api/conversations/{id}", delete_turn_handler)

    # Container file serving — lets the frontend (and agent-authored HTML) reference
    # container files by their real path instead of base64-encoding them.
    cfg = load_config()
    container_prefix = cfg.virtual_computer.container_working_dir
    app.router.add_route("GET", f"{container_prefix}/{{path:.*}}", container_file_handler)

    # UI routes
    app.router.add_route("GET", "/", index_handler)
    if UI_DIST_DIR.exists():
        app.router.add_static("/assets", UI_DIST_DIR / "assets", show_index=False)
    if STATIC_DIR.exists():
        app.router.add_static("/static", STATIC_DIR, show_index=False)
    return app


__all__ = ["create_app"]
