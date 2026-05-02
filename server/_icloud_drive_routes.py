"""HTTP routes for iCloud Drive pre-authentication and re-authentication.

These handle the SRP + 2FA flow that sets up the rclone config before
(or instead of) the normal integration add flow.  The preauth routes
are called *before* ``POST /api/integrations`` (the integration doesn't
exist yet).  The reauth routes are called on an existing integration
whose trust token has expired.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from aiohttp import web

from tools.integrations import mark_added

from ._integrations_routes import _error_response, _supervisor_rpc  # noqa: PLC2701

logger = logging.getLogger(__name__)


# ── preauth (before integration exists) ────────────────────────────────────


async def handle_preauth_icloud_drive(request: web.Request) -> web.Response:
    """``POST /api/integrations/preauth/icloud-drive`` — step 1: initiate SRP + 2FA.

    Body: ``{email, password}`` (Apple ID credentials, NOT app-specific).
    Returns ``{session_id, requires_2fa}``.
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

    email = body.get("email")
    password = body.get("password")
    if not isinstance(email, str) or not email:
        return _error_response({"code": "BAD_REQUEST", "message": "email is required"})
    if not isinstance(password, str) or not password:
        return _error_response({"code": "BAD_REQUEST", "message": "password is required"})

    from integrations._icloud_auth import (
        IcloudAuthError,
        IcloudAuthPasswordError,
        initiate_auth,
    )

    try:
        result = initiate_auth(email, password)
    except IcloudAuthPasswordError as exc:
        return _error_response({"code": "AUTH", "message": str(exc)})
    except IcloudAuthError as exc:
        return _error_response({"code": "UPSTREAM", "message": str(exc)})

    return web.json_response(result)


async def handle_preauth_icloud_drive_verify(request: web.Request) -> web.Response:
    """``POST /api/integrations/preauth/icloud-drive/verify`` — step 2: validate 2FA code.

    Body: ``{session_id, code}``.
    Returns ``{ok: true}`` on success.
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

    session_id = body.get("session_id")
    code = body.get("code")
    if not isinstance(session_id, str) or not session_id:
        return _error_response({"code": "BAD_REQUEST", "message": "session_id is required"})
    if not isinstance(code, str) or not code:
        return _error_response({"code": "BAD_REQUEST", "message": "code is required"})

    from integrations._icloud_auth import IcloudAuthError, complete_auth

    try:
        result = complete_auth(session_id, code)
    except IcloudAuthError as exc:
        return _error_response({"code": "AUTH", "message": str(exc)})

    return web.json_response(result)


# ── reauth (integration exists, trust token expired) ───────────────────────


async def handle_reauth(request: web.Request) -> web.Response:
    """``POST /api/integrations/{id}/reauth`` — initiate re-authentication.

    The supervisor reads the stored password from the vault and starts a
    new SRP handshake.  Returns ``{session_id, requires_2fa}``.
    """
    integration_id = request.match_info.get("id", "")
    if not integration_id:
        return _error_response({"code": "BAD_REQUEST", "message": "integration id is required"})

    try:
        resp = await _supervisor_rpc("reauth_init", {"id": integration_id})
    except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
        logger.warning("supervisor unreachable for reauth_init: %s", exc)
        return web.json_response(
            {"error": {"code": "UNAVAILABLE", "message": "Integrations service isn't running."}},
            status=503,
        )
    if "error" in resp:
        return _error_response(resp["error"])
    return web.json_response(resp["result"])


async def handle_reauth_verify(request: web.Request) -> web.Response:
    """``POST /api/integrations/{id}/reauth/verify`` — complete re-authentication.

    Body: ``{session_id, code}``.  The supervisor validates the 2FA code,
    writes a new trust token to the rclone config, and respawns the broker.
    Returns the updated integration record on success.
    """
    integration_id = request.match_info.get("id", "")
    if not integration_id:
        return _error_response({"code": "BAD_REQUEST", "message": "integration id is required"})

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

    session_id = body.get("session_id")
    code = body.get("code")
    if not isinstance(session_id, str) or not session_id:
        return _error_response({"code": "BAD_REQUEST", "message": "session_id is required"})
    if not isinstance(code, str) or not code:
        return _error_response({"code": "BAD_REQUEST", "message": "code is required"})

    try:
        resp = await _supervisor_rpc("reauth_verify", {
            "id": integration_id,
            "session_id": session_id,
            "code": code,
        })
    except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
        logger.warning("supervisor unreachable for reauth_verify: %s", exc)
        return web.json_response(
            {"error": {"code": "UNAVAILABLE", "message": "Integrations service isn't running."}},
            status=503,
        )
    if "error" in resp:
        return _error_response(resp["error"])

    # Refresh the tool-visibility cache
    result = resp["result"]
    mark_added(
        integration_id,
        result.get("slug") or "",
        result.get("capabilities") or (),
        result.get("state") or "running",
        bool(result.get("write_allowed", False)),
    )
    return web.json_response(result)


# ── registration ───────────────────────────────────────────────────────────


def register_icloud_drive_routes(app: web.Application) -> None:
    """Register iCloud Drive preauth + reauth routes on the application."""
    app.router.add_route(
        "POST", "/api/integrations/preauth/icloud-drive", handle_preauth_icloud_drive,
    )
    app.router.add_route(
        "POST", "/api/integrations/preauth/icloud-drive/verify", handle_preauth_icloud_drive_verify,
    )
    app.router.add_route(
        "POST", "/api/integrations/{id}/reauth", handle_reauth,
    )
    app.router.add_route(
        "POST", "/api/integrations/{id}/reauth/verify", handle_reauth_verify,
    )
