"""HTTP routes under ``/api/integrations`` — list + add + remove.

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
import re
from typing import Any

from aiohttp import web

from config import load_config
from tools.integrations import mark_added, mark_removed

logger = logging.getLogger(__name__)

_ERROR_STATUS = {
    "BAD_REQUEST": 400,
    "NOT_FOUND": 404,
    "AUTH": 409,           # credentials rejected by upstream — client can reconnect
    "WRITE_DENIED": 403,   # permission gate (not expected on admin routes but mapped for completeness)
    "UPSTREAM": 502,
    "INTERNAL": 500,
}

# Sanitize-only — turn arbitrary characters into the [a-z0-9_-] set the
# supervisor's regex demands. The supervisor still validates the result.
_SUFFIX_NON_ALLOWED = re.compile(r"[^a-z0-9_-]")
_SUFFIX_DASH_RUNS = re.compile(r"-+")


def _derive_suffix_from_email(auth_blob: dict[str, Any] | None) -> str | None:
    """Sanitize ``auth_blob['email']``'s local-part into a usable user suffix.

    Returns ``None`` if there's no email or the cleaned local-part is empty.
    The supervisor enforces the actual format invariant — this is just here
    so the frontend can submit credentials without thinking up an ID.
    """
    if not isinstance(auth_blob, dict):
        return None
    email = auth_blob.get("email")
    if not isinstance(email, str):
        return None
    local = email.split("@", 1)[0].lower()
    cleaned = _SUFFIX_DASH_RUNS.sub("-", _SUFFIX_NON_ALLOWED.sub("-", local)).strip("-")
    cleaned = cleaned[:48]
    return cleaned or None


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
    """``GET /api/integrations`` — non-secret metadata for every active integration."""
    try:
        resp = await _supervisor_rpc("list", {})
    except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
        logger.warning("supervisor unreachable for list: %s", exc)
        return web.json_response(
            {"error": {"code": "UNAVAILABLE", "message": "Integrations service isn't running."}},
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
          "label": "iCloud — Larry",
          "auth_blob": {"email": "...", "password": "..."},
          "write_allowed": false
        }

    The integration ID's user-suffix is derived from ``auth_blob['email']``
    by this handler before forwarding to the supervisor; clients don't
    pick it.

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

    # user_suffix is derived from auth_blob.email — clients never set it.
    # Keeps integration IDs deterministic and out of the user's mental model.
    derived = _derive_suffix_from_email(body.get("auth_blob"))
    if not derived:
        return _error_response(
            {"code": "BAD_REQUEST", "message": "auth_blob.email is required"}
        )
    body["user_suffix"] = derived

    try:
        resp = await _supervisor_rpc("add", body)
    except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
        logger.warning("supervisor unreachable for add: %s", exc)
        return web.json_response(
            {"error": {"code": "UNAVAILABLE", "message": "Integrations service isn't running."}},
            status=503,
        )
    if "error" in resp:
        return _error_response(resp["error"])

    # Update the app-server's tool-visibility cache so the agent sees the new
    # integration's tools on the next turn without a supervisor round-trip.
    # The supervisor's add response carries everything the cache needs (id,
    # slug, capabilities). Missing id/slug is a supervisor bug — surface it
    # as 502 rather than returning 201 with a corrupted cache.
    result = resp["result"]
    integration_id = result.get("id")
    slug = result.get("slug")
    if not (isinstance(integration_id, str) and isinstance(slug, str)):
        logger.error("supervisor add response missing id/slug: %r", result)
        return _error_response(
            {"code": "UPSTREAM", "message": "malformed add response"}
        )
    mark_added(
        integration_id,
        slug,
        result.get("capabilities") or (),
        result.get("state") or "running",
        bool(result.get("write_allowed", False)),
    )

    return web.json_response(result, status=201)


async def handle_update_integration(request: web.Request) -> web.Response:
    """``PATCH /api/integrations/{id}`` — update mutable fields on an integration.

    Body fields (each optional, at least one required): ``write_allowed``
    (bool) and ``label`` (non-empty string). Flipping ``write_allowed``
    triggers a broker respawn so the new ``WRITE_ALLOWED`` env takes effect
    (brief downtime ~SIGTERM grace + READY handshake). Updating ``label``
    is meta-only — no respawn.

    On success: ``200 OK`` with the updated record. On unknown id: ``404``.
    """
    integration_id = request.match_info.get("id", "")
    if not integration_id:
        return _error_response(
            {"code": "BAD_REQUEST", "message": "integration id is required"}
        )

    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.json_response(
            {"error": {"code": "BAD_REQUEST", "message": "invalid JSON body"}},
            status=400,
        )
    if not isinstance(body, dict):
        return _error_response(
            {"code": "BAD_REQUEST", "message": "JSON body must be an object"}
        )

    rpc_args: dict[str, Any] = {"id": integration_id}
    if "write_allowed" in body:
        if not isinstance(body["write_allowed"], bool):
            return _error_response(
                {"code": "BAD_REQUEST", "message": "'write_allowed' must be a bool"}
            )
        rpc_args["write_allowed"] = body["write_allowed"]
    if "label" in body:
        if not isinstance(body["label"], str) or not body["label"]:
            return _error_response(
                {"code": "BAD_REQUEST", "message": "'label' must be a non-empty string"}
            )
        rpc_args["label"] = body["label"]
    if "write_allowed" not in rpc_args and "label" not in rpc_args:
        return _error_response(
            {"code": "BAD_REQUEST", "message": "'write_allowed' and/or 'label' required"}
        )

    try:
        resp = await _supervisor_rpc("update", rpc_args)
    except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
        logger.warning("supervisor unreachable for update: %s", exc)
        return web.json_response(
            {"error": {"code": "UNAVAILABLE", "message": "Integrations service isn't running."}},
            status=503,
        )
    if "error" in resp:
        return _error_response(resp["error"])

    # Refresh the in-process cache with the new write_allowed value so the
    # agent's next turn surfaces tools matching the new policy. The
    # supervisor's update response carries the same shape as add.
    result = resp["result"]
    mark_added(
        integration_id,
        result.get("slug") or "",
        result.get("capabilities") or (),
        result.get("state") or "running",
        bool(result.get("write_allowed", False)),
    )
    return web.json_response(result)


async def handle_remove_integration(request: web.Request) -> web.Response:
    """``DELETE /api/integrations/{id}`` — tear down a registered integration.

    Calls the supervisor's ``remove`` verb, which SIGTERMs the broker and
    deletes the vault files. On success the app server clears its tool-
    visibility cache entry so the agent's next turn no longer sees tools
    bound to this integration.

    On success: ``204 No Content``. On unknown id: ``404``.
    """
    integration_id = request.match_info.get("id", "")
    if not integration_id:
        return _error_response(
            {"code": "BAD_REQUEST", "message": "integration id is required"}
        )

    try:
        resp = await _supervisor_rpc("remove", {"id": integration_id})
    except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
        logger.warning("supervisor unreachable for remove: %s", exc)
        return web.json_response(
            {"error": {"code": "UNAVAILABLE", "message": "Integrations service isn't running."}},
            status=503,
        )
    if "error" in resp:
        return _error_response(resp["error"])

    mark_removed(integration_id)
    return web.Response(status=204)


def register_integrations_routes(app: web.Application) -> None:
    """Register ``/api/integrations`` routes on the application."""
    app.router.add_route("GET", "/api/integrations", handle_list_integrations)
    app.router.add_route("POST", "/api/integrations", handle_add_integration)
    app.router.add_route(
        "PATCH", "/api/integrations/{id}", handle_update_integration,
    )
    app.router.add_route(
        "DELETE", "/api/integrations/{id}", handle_remove_integration,
    )
