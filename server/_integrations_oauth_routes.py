"""HTTP routes for the OAuth integration flow (start / callback / status).

The loopback OAuth handshake lives here; CRUD routes for integrations live
in ``_integrations_routes``. Both talk to the supervisor via
``integrations.supervisor_client``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from aiohttp import web

from config import load_config
from integrations import supervisor_client
from integrations.supervisor_client import SupervisorError
from integrations.permissions import permissions_from_dict
from server._integrations_http import error_response
from server._oauth import OAuthIntegrationManager
from tools.integrations import mark_added

logger = logging.getLogger(__name__)

# One OAuth state machine per app-server process, shared across all
# OAuth-related route handlers. Pending flows live in this object's
# memory only — restart drops them, user retries.
_oauth = OAuthIntegrationManager()


class _StringRequired(ValueError):
    """Raised by :func:`_require_str` when a key is missing or non-string."""


# Maps internal field names to the user-facing label that appears in
# error messages. Keeps validation copy in plain language ("Email
# address") rather than leaking implementation field names ("auth_blob.email").
_FIELD_LABEL = {
    "client_id": "Client ID",
    "client_secret": "Client Secret",
    "label": "Label",
    "slug": "Provider",
    "user_suffix": "Account suffix",
}


def _require_str(body: dict, key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value:
        label = _FIELD_LABEL.get(key, key.replace("_", " ").capitalize())
        msg = f"{label} can't be empty."
        raise _StringRequired(msg)
    return value


def _oauth_popup_html(title: str, body: str) -> str:
    """Tiny self-closing HTML page rendered in the OAuth popup window.

    The popup attempts to ``window.close()`` itself after a short delay,
    falling back to the title + body if the browser refuses to close
    (some browsers block ``close()`` on windows that weren't opened by
    script — but ours always are).
    """
    safe_title = title.replace("<", "&lt;").replace(">", "&gt;")
    safe_body = body.replace("<", "&lt;").replace(">", "&gt;")
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{safe_title}</title>"
        "<style>body{font-family:system-ui,sans-serif;background:#0c0c0e;"
        "color:#e6e6e6;display:flex;flex-direction:column;align-items:center;"
        "justify-content:center;height:100vh;margin:0;padding:24px;text-align:center}"
        "h1{font-size:18px;font-weight:500;margin:0 0 8px}"
        "p{font-size:13px;color:#9aa0a6;margin:0}</style>"
        "</head><body>"
        f"<h1>{safe_title}</h1><p>{safe_body}</p>"
        "<script>setTimeout(()=>window.close(),1500)</script>"
        "</body></html>"
    )


async def _supervisor_call(verb: str, args: dict[str, Any]) -> dict[str, Any]:
    """Call a supervisor verb with a 60s timeout."""
    app_sock = load_config().integrations.app_sock_path
    return await asyncio.wait_for(
        supervisor_client.call(verb, args, app_sock_path=app_sock),
        timeout=60.0,
    )


async def handle_start_oauth(request: web.Request) -> web.Response:
    """``POST /api/integrations/oauth/start`` — begin a loopback-flow add.

    Request body (JSON)::

        {
          "slug": "google_workspace",
          "user_suffix": "personal",
          "label": "Google Workspace · you@gmail.com",
          "client_id": "...",
          "client_secret": "...",
          "scopes": ["https://www.googleapis.com/auth/gmail.readonly", ...],
          "permissions": {"email": "rw", "calendar": "r"}
        }

    On success: ``200 OK`` with ``{state, authorize_url, expires_in}``.
    The UI opens ``authorize_url`` in a popup; Google bounces the user
    back to :func:`handle_oauth_callback` with the code attached.

    The ``redirect_uri`` is computed *here*, not by the client, so we
    can guarantee it points at this instance — the redirect is what makes
    the loopback flow work in the first place. We derive the URL from the
    inbound request's scheme + host.
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

    scopes = body.get("scopes")
    if not isinstance(scopes, list) or not all(
        isinstance(s, str) and s for s in scopes
    ):
        return error_response(
            "BAD_REQUEST", "Pick at least one capability before authorizing.",
        )

    # Build the redirect URI from the request's host so it always points
    # back to *this* instance — whether the user is on localhost:9090
    # (manual-test), 127.0.0.1:8080 (dev), or any other configuration.
    # Google's Desktop-app client type accepts any http://localhost or
    # http://127.0.0.1 URL without needing the specific port pre-registered.
    redirect_uri = (
        f"{request.scheme}://{request.host}/api/integrations/oauth/callback"
    )

    perms_raw = body.get("permissions")
    if not isinstance(perms_raw, dict):
        perms_raw = {}

    try:
        pending = _oauth.start(
            slug=_require_str(body, "slug"),
            user_suffix=_require_str(body, "user_suffix"),
            label=_require_str(body, "label"),
            client_id=_require_str(body, "client_id"),
            client_secret=_require_str(body, "client_secret"),
            scopes=scopes,
            permissions_raw=perms_raw,
            redirect_uri=redirect_uri,
        )
    except _StringRequired as exc:
        return error_response("BAD_REQUEST", str(exc))
    except ValueError as exc:
        return error_response("BAD_REQUEST", str(exc))

    return web.json_response({
        "state": pending.state,
        "authorize_url": pending.authorize_url,
        "expires_in": int(pending.expires_at - time.time()),
    })


async def handle_oauth_callback(request: web.Request) -> web.Response:
    """``GET /api/integrations/oauth/callback`` — Google's redirect target.

    Google sends the user's browser here with ``?code=...&state=...``
    after the consent screen. We exchange the code for tokens locally
    (via :class:`OAuthIntegrationManager`), then POST the resulting auth_blob to the
    supervisor's existing ``add`` verb — same path the app-password
    flow uses. The popup auto-closes; the main UI's poll picks up the
    new ``status=success``.

    Errors get the same HTML-popup treatment — the popup closes, the
    main tab's poll picks up the failure status. We don't try to
    render a full error page inside the popup.
    """
    state = request.query.get("state", "")
    code = request.query.get("code")
    error = request.query.get("error")  # access_denied if user clicked Cancel

    if not state:
        return web.Response(
            text=_oauth_popup_html(
                "Sign-in link wasn't quite right",
                "Close this window and start the sign-in.",
            ),
            content_type="text/html",
            status=400,
        )

    pending = _oauth.status(state)
    if pending is None:
        return web.Response(
            text=_oauth_popup_html(
                "Sign-in session expired",
                "Close this window and start the sign-in again.",
            ),
            content_type="text/html",
            status=404,
        )

    auth_blob = await _oauth.fetch_tokens(state=state, code=code, error=error)
    if auth_blob is None:
        # The flow already marked the pending record terminal (denied /
        # expired / error). Inform the user via the popup; main tab's
        # poll picks up the right status.
        terminal = _oauth.status(state)
        if terminal and terminal.status == "denied":
            heading, body = "Sign-in cancelled", "You can close this window."
        else:
            heading, body = (
                "Couldn't complete sign-in",
                (terminal.error_message if terminal else None)
                or "Try again from the main window.",
            )
        return web.Response(
            text=_oauth_popup_html(heading, body),
            content_type="text/html",
        )

    # Tokens in hand — hand off to the supervisor's existing add path.
    add_body = {
        "slug": pending.slug,
        "user_suffix": pending.user_suffix,
        "label": pending.label,
        "auth_blob": auth_blob,
        "permissions": pending.permissions_raw,
    }
    try:
        result = await _supervisor_call("add", add_body)
    except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
        logger.warning("supervisor unreachable for add (oauth path): %s", exc)
        _oauth.mark_error(
            state, "UNAVAILABLE",
            "Integrations service isn't running.",
        )
        return web.Response(
            text=_oauth_popup_html(
                "Integrations service unreachable",
                "Try again in a moment.",
            ),
            content_type="text/html",
            status=503,
        )
    except SupervisorError as exc:
        # Truncate + sanitise the message before it hits the popup.
        safe_msg = "".join(
            c for c in exc.message[:200] if c.isprintable()
        ) or "Try again."
        _oauth.mark_error(state, exc.code, safe_msg)
        return web.Response(
            text=_oauth_popup_html("Couldn't add this integration", safe_msg),
            content_type="text/html",
        )

    integration_id = result.get("id")
    slug = result.get("slug")
    if not (isinstance(integration_id, str) and isinstance(slug, str)):
        _oauth.mark_error(
            state, "UPSTREAM", "Something went wrong on our end. Try again.",
        )
        return web.Response(
            text=_oauth_popup_html(
                "Something went wrong",
                "Try again from Computron.",
            ),
            content_type="text/html",
            status=502,
        )

    # Warm the agent's tool cache so the new integration's tools appear
    # on the next turn — same hook the app-password add path uses.
    perms_result = result.get("permissions")
    mark_added(
        integration_id,
        slug,
        permissions_from_dict(perms_result) if isinstance(perms_result, dict) else {},
        result.get("state") or "running",
    )
    _oauth.mark_success(state, integration_id)
    return web.Response(
        text=_oauth_popup_html("Signed in", "You can close this window."),
        content_type="text/html",
    )


async def handle_oauth_status(request: web.Request) -> web.Response:
    """``GET /api/integrations/oauth/status/{state}`` — poll OAuth status.

    Returns one of::

        {"status": "pending"}
        {"status": "success", "integration_id": "google_workspace_personal"}
        {"status": "denied"}
        {"status": "expired"}
        {"status": "error", "error": {"code": "...", "message": "..."}}
    """
    state = request.match_info.get("state", "")
    if not state:
        return error_response(
            "BAD_REQUEST",
            "Sign-in session is missing. Try again from Computron.",
        )
    pending = _oauth.status(state)
    if pending is None:
        return error_response(
            "NOT_FOUND",
            "Sign-in session expired. Try again from Computron.",
        )
    out: dict[str, Any] = {"status": pending.status}
    if pending.integration_id is not None:
        out["integration_id"] = pending.integration_id
    if pending.error_code is not None:
        out["error"] = {
            "code": pending.error_code,
            "message": pending.error_message or "",
        }
    return web.json_response(out)


def register_oauth_routes(app: web.Application) -> None:
    """Register ``/api/integrations/oauth/*`` routes on the application."""
    app.router.add_route(
        "POST", "/api/integrations/oauth/start", handle_start_oauth,
    )
    app.router.add_route(
        "GET", "/api/integrations/oauth/callback", handle_oauth_callback,
    )
    app.router.add_route(
        "GET", "/api/integrations/oauth/status/{state}", handle_oauth_status,
    )
