"""HTTP routes under ``/api/integrations`` — CRUD for integrations.

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
from integrations import supervisor_client
from integrations.supervisor_client import SupervisorError
from server._integrations_http import error_response
from tools.integrations import mark_added, mark_removed

logger = logging.getLogger(__name__)


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


async def _supervisor_call(verb: str, args: dict[str, Any]) -> dict[str, Any]:
    """Call a supervisor verb with a 60s timeout.

    The supervisor's slowest verbs (``add`` / ``update`` write_allowed) wait
    on a 30s broker READY handshake plus SIGTERM grace, so 60s gives headroom
    for the worst legit case while bounding hangs if the supervisor itself is
    wedged. ``TimeoutError`` is an ``OSError`` subclass on 3.11+, so route
    handlers catch it through the ``except OSError`` arm and return a 503.
    """
    app_sock = load_config().integrations.app_sock_path
    return await asyncio.wait_for(
        supervisor_client.call(verb, args, app_sock_path=app_sock),
        timeout=60.0,
    )


async def handle_list_integrations(_request: web.Request) -> web.Response:
    """``GET /api/integrations`` — non-secret metadata for every active integration."""
    try:
        result = await _supervisor_call("list", {})
    except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
        logger.warning("supervisor unreachable for list: %s", exc)
        return web.json_response(
            {"error": {"code": "UNAVAILABLE", "message": "Integrations service isn't running."}},
            status=503,
        )
    except SupervisorError as exc:
        return error_response(exc.code, exc.message)
    return web.json_response(result)


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
            {"error": {"code": "BAD_REQUEST",
                       "message": "Couldn't read that request. Refresh and try again."}},
            status=400,
        )
    if not isinstance(body, dict):
        return web.json_response(
            {"error": {"code": "BAD_REQUEST",
                       "message": "Couldn't read that request. Refresh and try again."}},
            status=400,
        )

    # user_suffix is derived from auth_blob.email — clients never set it.
    # Keeps integration IDs deterministic and out of the user's mental model.
    derived = _derive_suffix_from_email(body.get("auth_blob"))
    if not derived:
        return error_response("BAD_REQUEST", "Email address is required.")
    body["user_suffix"] = derived

    try:
        result = await _supervisor_call("add", body)
    except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
        logger.warning("supervisor unreachable for add: %s", exc)
        return web.json_response(
            {"error": {"code": "UNAVAILABLE", "message": "Integrations service isn't running."}},
            status=503,
        )
    except SupervisorError as exc:
        return error_response(exc.code, exc.message)

    # Update the app-server's tool-visibility cache so the agent sees the new
    # integration's tools on the next turn without a supervisor round-trip.
    # The supervisor's add response carries everything the cache needs (id,
    # slug, capabilities). Missing id/slug is a supervisor bug — surface it
    # as 502 rather than returning 201 with a corrupted cache.
    integration_id = result.get("id")
    slug = result.get("slug")
    if not (isinstance(integration_id, str) and isinstance(slug, str)):
        logger.error("supervisor add response missing id/slug: %r", result)
        return error_response("UPSTREAM", "Something went wrong on our end. Try again.")
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
        return error_response(
            "BAD_REQUEST",
            "Couldn't tell which integration to update. Refresh and try again.",
        )

    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return web.json_response(
            {"error": {"code": "BAD_REQUEST",
                       "message": "Couldn't read that request. Refresh and try again."}},
            status=400,
        )
    if not isinstance(body, dict):
        return error_response(
            "BAD_REQUEST",
            "Couldn't read that request. Refresh and try again.",
        )

    rpc_args: dict[str, Any] = {"id": integration_id}
    if "write_allowed" in body:
        if not isinstance(body["write_allowed"], bool):
            return error_response("BAD_REQUEST", "Write permission must be on or off.")
        rpc_args["write_allowed"] = body["write_allowed"]
    if "label" in body:
        if not isinstance(body["label"], str) or not body["label"]:
            return error_response("BAD_REQUEST", "Label can't be empty.")
        rpc_args["label"] = body["label"]
    if "write_allowed" not in rpc_args and "label" not in rpc_args:
        return error_response("BAD_REQUEST", "Nothing to update.")

    try:
        result = await _supervisor_call("update", rpc_args)
    except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
        logger.warning("supervisor unreachable for update: %s", exc)
        return web.json_response(
            {"error": {"code": "UNAVAILABLE", "message": "Integrations service isn't running."}},
            status=503,
        )
    except SupervisorError as exc:
        return error_response(exc.code, exc.message)

    # Refresh the in-process cache with the new write_allowed value so the
    # agent's next turn surfaces tools matching the new policy. The
    # supervisor's update response carries the same shape as add.
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
        return error_response(
            "BAD_REQUEST",
            "Couldn't tell which integration to remove. Refresh and try again.",
        )

    try:
        await _supervisor_call("remove", {"id": integration_id})
    except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
        logger.warning("supervisor unreachable for remove: %s", exc)
        return web.json_response(
            {"error": {"code": "UNAVAILABLE", "message": "Integrations service isn't running."}},
            status=503,
        )
    except SupervisorError as exc:
        return error_response(exc.code, exc.message)

    mark_removed(integration_id)
    return web.Response(status=204)


def register_integrations_routes(app: web.Application) -> None:
    """Register ``/api/integrations`` CRUD routes on the application."""
    app.router.add_route("GET", "/api/integrations", handle_list_integrations)
    app.router.add_route("POST", "/api/integrations", handle_add_integration)
    app.router.add_route(
        "PATCH", "/api/integrations/{id}", handle_update_integration,
    )
    app.router.add_route(
        "DELETE", "/api/integrations/{id}", handle_remove_integration,
    )
