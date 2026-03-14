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

from server.message_handler import AVAILABLE_AGENTS, handle_user_message, reset_message_history
from sdk.providers import get_provider
from sdk.loop import is_turn_active, queue_nudge, request_stop
from agents.types import Data, LLMOptions
from config import load_config
from tools.custom_tools.registry import delete_tool, list_tools
from tools.memory import forget as forget_memory
from tools.memory import load_memory, set_key_hidden
from tools.skills._extractor import skill_extraction_loop
from tools.skills._registry import (
    delete_skill as _delete_skill,
    list_skills as _list_skills,
    toggle_skill as _toggle_skill,
)
from tools.conversations._store import (
    delete_conversation as _delete_conversation,
    list_conversations as _list_conversations,
    load_conversation as _load_conversation,
)

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
    session_id: str | None = None
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
    from sdk.events import AssistantResponse


async def stream_events(
    request: Request,
    events: AsyncIterator[AssistantResponse],  # iterator of AssistantResponse
) -> StreamResponse:
    """Stream JSONL events to the client.

    Args:
        request: Incoming aiohttp request.
        events: Async iterator yielding `AssistantResponse` instances produced by
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
            data_out = event.model_dump(mode="json", exclude_none=True)
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

    # If this session already has an active agent, queue the message as a nudge
    if is_turn_active(payload.session_id):
        queue_nudge(payload.session_id or "default", user_query)
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
            session_id=payload.session_id, agent=payload.agent,
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
    session_id = request.query.get("session_id")
    request_stop(session_id=session_id)
    return web.json_response({"ok": True})


async def delete_history_handler(request: Request) -> Response:
    """Clear chat history for a session."""
    session_id = request.query.get("session_id")
    reset_message_history(session_id=session_id)
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


async def list_skills_handler(_request: Request) -> Response:
    """Return all skill definitions as JSON."""
    skills = _list_skills(active_only=False)
    data = [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "agent_scope": s.agent_scope,
            "category": s.category,
            "confidence": s.confidence,
            "usage_count": s.usage_count,
            "success_count": s.success_count,
            "failure_count": s.failure_count,
            "active": s.active,
            "steps": len(s.steps),
            "created_at": s.created_at,
            "last_used_at": s.last_used_at,
        }
        for s in skills
    ]
    return web.json_response(data)


async def delete_skill_handler(request: Request) -> Response:
    """Delete a skill by name."""
    name = request.match_info["name"]
    found = _delete_skill(name)
    if not found:
        return web.json_response({"error": f"Skill '{name}' not found"}, status=404)
    return web.Response(status=204)


async def patch_skill_handler(request: Request) -> Response:
    """Toggle a skill's active state."""
    name = request.match_info["name"]
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.json_response({"error": "Invalid JSON body"}, status=400)
    active = body.get("active")
    if active is None:
        return web.json_response({"error": "Missing 'active' field"}, status=400)
    found = _toggle_skill(name, active=bool(active))
    if not found:
        return web.json_response({"error": f"Skill '{name}' not found"}, status=404)
    return web.Response(status=204)


async def list_conversations_handler(request: Request) -> Response:
    """Return conversation index entries (paginated)."""
    limit = int(request.query.get("limit", "50"))
    offset = int(request.query.get("offset", "0"))
    outcome = request.query.get("outcome")
    entries = _list_conversations(limit=limit, offset=offset, outcome=outcome)
    data = [e.model_dump() for e in entries]
    return web.json_response(data)


async def get_conversation_handler(request: Request) -> Response:
    """Return a full conversation transcript."""
    conv_id = request.match_info["id"]
    record = _load_conversation(conv_id)
    if record is None:
        return web.json_response({"error": "Conversation not found"}, status=404)
    return web.json_response(record.model_dump())


async def delete_conversation_handler(request: Request) -> Response:
    """Delete a conversation by ID."""
    conv_id = request.match_info["id"]
    found = _delete_conversation(conv_id)
    if not found:
        return web.json_response({"error": "Conversation not found"}, status=404)
    return web.Response(status=204)


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

    # Skills API
    app.router.add_route("GET", "/api/skills", list_skills_handler)
    app.router.add_route("DELETE", "/api/skills/{name}", delete_skill_handler)
    app.router.add_route("PATCH", "/api/skills/{name}", patch_skill_handler)

    # Conversations API
    app.router.add_route("GET", "/api/conversations", list_conversations_handler)
    app.router.add_route("GET", "/api/conversations/{id}", get_conversation_handler)
    app.router.add_route("DELETE", "/api/conversations/{id}", delete_conversation_handler)

    # Start background skill extraction loop
    async def _start_extraction(app: web.Application) -> None:
        app["_skill_extraction_task"] = asyncio.create_task(skill_extraction_loop())

    async def _stop_extraction(app: web.Application) -> None:
        task = app.get("_skill_extraction_task")
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app.on_startup.append(_start_extraction)
    app.on_cleanup.append(_stop_extraction)

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
