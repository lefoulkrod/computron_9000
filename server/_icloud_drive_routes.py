"""HTTP routes for iCloud Drive pre-authentication (Apple ID sign-in + 2FA).

iCloud Drive has no app-specific-password path and no OAuth — connecting it
needs a live Apple ID sign-in plus a 2FA code, which together yield a
``trust_token``. These two routes drive that exchange; the UI then passes
``{email, password, trust_token}`` through the normal ``POST /api/integrations``
flow, where the supervisor injects them as rclone env vars.

There's no auth layer here for the same reason the other integration routes
have none — the app server and supervisor share a container, and HTTP-level
auth is the frontend's concern.
"""

from __future__ import annotations

import json
import logging

from aiohttp import web

from integrations._icloud_auth import (
    IcloudAuthError,
    IcloudAuthPasswordError,
    complete_auth,
    initiate_auth,
)
from server._integrations_http import error_response

logger = logging.getLogger(__name__)


async def _json_body(request: web.Request) -> dict | web.Response:
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return error_response("BAD_REQUEST", "Couldn't read that request. Refresh and try again.")
    if not isinstance(body, dict):
        return error_response("BAD_REQUEST", "Couldn't read that request. Refresh and try again.")
    return body


async def handle_icloud_drive_preauth_start(request: web.Request) -> web.Response:
    """``POST /api/integrations/icloud-drive/preauth`` — sign in, trigger 2FA.

    Body: ``{"email": "...", "password": "..."}`` (the Apple ID account
    password, not an app-specific one).

    On success: ``200 OK`` with ``{"session_id": "...", "requires_2fa": true}``.
    """
    body = await _json_body(request)
    if isinstance(body, web.Response):
        return body
    email = body.get("email")
    password = body.get("password")
    if not isinstance(email, str) or not email:
        return error_response("BAD_REQUEST", "Apple ID email is required.")
    if not isinstance(password, str) or not password:
        return error_response("BAD_REQUEST", "Apple ID password is required.")

    try:
        result = await initiate_auth(email, password)
    except IcloudAuthPasswordError as exc:
        return error_response("AUTH", str(exc))
    except IcloudAuthError as exc:
        return error_response("UPSTREAM", str(exc))
    return web.json_response(result)


async def handle_icloud_drive_preauth_verify(request: web.Request) -> web.Response:
    """``POST /api/integrations/icloud-drive/preauth/verify`` — submit the 2FA code.

    Body: ``{"session_id": "...", "code": "123456"}``.

    On success: ``200 OK`` with ``{"trust_token": "..."}``.
    """
    body = await _json_body(request)
    if isinstance(body, web.Response):
        return body
    session_id = body.get("session_id")
    code = body.get("code")
    if not isinstance(session_id, str) or not session_id:
        return error_response("BAD_REQUEST", "Sign-in session is missing. Start over.")
    if not isinstance(code, str) or not code:
        return error_response("BAD_REQUEST", "The 2FA code is required.")

    try:
        result = await complete_auth(session_id, code)
    except IcloudAuthError as exc:
        return error_response("AUTH", str(exc))
    return web.json_response(result)


def register_icloud_drive_routes(app: web.Application) -> None:
    """Register ``/api/integrations/icloud-drive/*`` routes."""
    app.router.add_route(
        "POST", "/api/integrations/icloud-drive/preauth", handle_icloud_drive_preauth_start,
    )
    app.router.add_route(
        "POST", "/api/integrations/icloud-drive/preauth/verify", handle_icloud_drive_preauth_verify,
    )
