"""HTTP route handlers for conversation sessions.

Endpoints:
    GET    /api/conversations/sessions                        — list summaries
    POST   /api/conversations/sessions/{id}/resume            — load history + preview state
    PUT    /api/conversations/sessions/{id}/preview-state     — persist preview tabs
    DELETE /api/conversations/sessions/{id}                   — delete a conversation
"""

import json

from aiohttp import web
from aiohttp.web import Request, Response

from conversations import (
    delete_conversation,
    list_conversations,
    save_preview_state,
)
from server.message_handler import resume_conversation


async def list_conversations_handler(_request: Request) -> Response:
    """Return past conversation summaries for the conversations panel."""
    summaries = list_conversations()
    data = [s.model_dump() for s in summaries]
    return web.json_response(data)


async def delete_conversation_handler(request: Request) -> Response:
    """Delete a conversation and all its turns/history."""
    conversation_id = request.match_info["conversation_id"]
    found = delete_conversation(conversation_id)
    if not found:
        return web.json_response({"error": "Conversation not found"}, status=404)
    return web.Response(status=204)


async def resume_conversation_handler(request: Request) -> Response:
    """Resume a past conversation by loading its full-fidelity history."""
    conversation_id = request.match_info["conversation_id"]
    data = await resume_conversation(conversation_id)
    if data is None:
        return web.json_response({"error": "Conversation not found"}, status=404)
    return web.json_response({
        "conversation_id": conversation_id,
        "messages": data["messages"],
        "events": data["events"],
        "preview_state": data["preview_state"],
    })


async def save_preview_state_handler(request: Request) -> Response:
    """Persist the user's preview-panel tab state for a conversation.

    The body is the full preview-state dict; it replaces any prior value.
    """
    conversation_id = request.match_info["conversation_id"]
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.json_response({"error": "Invalid JSON body"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"error": "Body must be a JSON object"}, status=400)
    save_preview_state(conversation_id, body)
    return web.Response(status=204)


def register_conversation_routes(app: web.Application) -> None:
    """Register conversation session routes on the application.

    The collection route is registered before the per-id wildcard so the
    aiohttp matcher doesn't accidentally treat `sessions` as an id.
    """
    app.router.add_route("GET", "/api/conversations/sessions", list_conversations_handler)
    app.router.add_route("POST", "/api/conversations/sessions/{conversation_id}/resume", resume_conversation_handler)
    app.router.add_route("PUT", "/api/conversations/sessions/{conversation_id}/preview-state", save_preview_state_handler)
    app.router.add_route("DELETE", "/api/conversations/sessions/{conversation_id}", delete_conversation_handler)


__all__ = ["register_conversation_routes"]
