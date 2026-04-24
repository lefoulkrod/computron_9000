"""HTTP routes under ``/api/integrations`` — add + list.

Handlers talk to the supervisor directly over its Unix Domain Socket using
the same length-prefixed JSON framing the supervisor serves. The supervisor
RPC logic is inlined in ``_supervisor_rpc`` (module-local helper) rather than
factored into a separate client module — walking-skeleton scope.

No auth layer on these routes today: the app server + supervisor run in the
same container, and the supervisor's ``app.sock`` is already group-gated to
the ``computron`` UID at the filesystem level. HTTP-level auth is a separate
concern handled by the frontend.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from aiohttp import web

from config import load_config
from tools.integrations import mark_added

logger = logging.getLogger(__name__)

_ERROR_STATUS = {
    "BAD_REQUEST": 400,
    "NOT_FOUND": 404,
    "AUTH": 409,           # credentials rejected by upstream — client can reconnect
    "WRITE_DENIED": 403,   # permission gate (not expected on admin routes but mapped for completeness)
    "UPSTREAM": 502,
    "INTERNAL": 500,
}


async def _supervisor_rpc(verb: str, args: dict[str, Any]) -> dict[str, Any]:
    """One-shot RPC: open UDS, send one frame, read one frame, close."""
    app_sock = load_config().integrations.app_sock_path
    reader, writer = await asyncio.open_unix_connection(app_sock)
    try:
        body = json.dumps({"id": 1, "verb": verb, "args": args}).encode("utf-8")
        writer.write(len(body).to_bytes(4, "big") + body)
        await writer.drain()
        length = int.from_bytes(await reader.readexactly(4), "big")
        return json.loads(await reader.readexactly(length))
    finally:
        writer.close()
        await writer.wait_closed()


def _error_response(error: dict[str, Any]) -> web.Response:
    """Map a supervisor error frame to an HTTP response.

    Broker/supervisor error codes (``BAD_REQUEST`` / ``NOT_FOUND`` / ``AUTH`` /
    ``UPSTREAM`` / ``INTERNAL``) become their conventional HTTP statuses; the
    body echoes the ``{code, message}`` pair for the frontend to surface.
    """
    code = error.get("code", "INTERNAL")
    status = _ERROR_STATUS.get(code, 500)
    return web.json_response({"error": error}, status=status)


async def handle_list_integrations(_request: web.Request) -> web.Response:
    """``GET /api/integrations`` — returns non-secret metadata for every
    currently registered integration."""
    try:
        resp = await _supervisor_rpc("list", {})
    except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
        logger.warning("supervisor unreachable for list: %s", exc)
        return web.json_response(
            {"error": {"code": "UNAVAILABLE", "message": "supervisor not reachable"}},
            status=503,
        )
    if "error" in resp:
        return _error_response(resp["error"])
    return web.json_response(resp["result"])


async def handle_add_integration(request: web.Request) -> web.Response:
    """``POST /api/integrations`` — register a new integration.

    Request body (JSON)::

        {
          "slug": "icloud",
          "user_suffix": "personal",
          "label": "iCloud — Larry",
          "auth_blob": {"email": "...", "password": "..."},
          "write_allowed": false
        }

    On success: ``201 Created`` with ``{id, socket}`` (the broker's UDS path,
    for debugging — callers normally don't touch it directly).
    """
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.json_response(
            {"error": {"code": "BAD_REQUEST", "message": "invalid JSON body"}},
            status=400,
        )
    if not isinstance(body, dict):
        return web.json_response(
            {"error": {"code": "BAD_REQUEST", "message": "body must be a JSON object"}},
            status=400,
        )

    try:
        resp = await _supervisor_rpc("add", body)
    except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
        logger.warning("supervisor unreachable for add: %s", exc)
        return web.json_response(
            {"error": {"code": "UNAVAILABLE", "message": "supervisor not reachable"}},
            status=503,
        )
    if "error" in resp:
        return _error_response(resp["error"])

    # Update the app-server's tool-visibility cache so the agent sees the new
    # integration's tools on the next turn without a supervisor round-trip.
    # The slug comes from the original request (the supervisor already
    # validated it).
    result = resp["result"]
    slug = body.get("slug")
    if isinstance(slug, str) and isinstance(result.get("id"), str):
        mark_added(result["id"], slug)

    return web.json_response(result, status=201)


def register_integrations_routes(app: web.Application) -> None:
    """Register ``/api/integrations`` routes on the application."""
    app.router.add_route("GET", "/api/integrations", handle_list_integrations)
    app.router.add_route("POST", "/api/integrations", handle_add_integration)
