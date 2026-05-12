"""iCloud Drive pre-authentication — direct Apple ID sign-in + 2FA.

Drives a two-step flow for the add-integration wizard:

1. :func:`initiate_auth` — POST the Apple ID + password, which triggers Apple
   to push a 2FA code to the user's trusted devices. Returns a session id.
2. :func:`complete_auth` — POST the 2FA code, then trust the session, and
   return the long-lived ``trust_token``.

The trust token (plus the Apple ID and password) is what the supervisor later
injects into rclone's ``RCLONE_CONFIG_DEFAULT_*`` env vars so the broker can
talk to iCloud Drive without re-doing 2FA on every spawn.

Pending sessions are held in process memory only — a restart drops them and
the user starts over. Single-user system, so the footprint is negligible.

Note: Apple's auth surface is undocumented and changes; if a step starts
returning unexpected statuses, that's the first place to look.
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

_AUTH_ENDPOINT = "https://idmsa.apple.com/appleauth/auth"
_SETUP_ENDPOINT = "https://setup.icloud.com/setup/ws/1"

# Public widget key Apple's own web sign-in uses. Not a secret.
_APPLE_WIDGET_KEY = "83545bf919730e51dbfba24e7e8a78d2"

_SESSION_TTL_SECONDS = 600.0


class IcloudAuthError(Exception):
    """The sign-in flow failed for a reason worth surfacing to the user."""


class IcloudAuthPasswordError(IcloudAuthError):
    """Apple rejected the Apple ID / password pair."""


@dataclass
class _PendingAuth:
    email: str
    password: str
    session: aiohttp.ClientSession
    scnt: str | None = None
    apple_session_id: str | None = None
    created: float = field(default_factory=time.monotonic)

    @property
    def expired(self) -> bool:
        return (time.monotonic() - self.created) > _SESSION_TTL_SECONDS


_pending: dict[str, _PendingAuth] = {}


def _gc() -> None:
    for sid in [sid for sid, p in _pending.items() if p.expired]:
        stale = _pending.pop(sid, None)
        if stale is not None:
            # Best-effort: drop the aiohttp session for an abandoned flow.
            # We don't await it here; the connector is closed on GC.
            stale.session.detach()


def _auth_headers(pending: _PendingAuth | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/javascript",
        "Content-Type": "application/json",
        "X-Apple-Widget-Key": _APPLE_WIDGET_KEY,
        "X-Apple-OAuth-Client-Id": _APPLE_WIDGET_KEY,
        "X-Apple-I-FD-Client-Info": json.dumps(
            {"U": "Mozilla/5.0", "L": "en-US", "Z": "GMT+00:00", "V": "1.1", "F": ""},
        ),
    }
    if pending is not None:
        if pending.apple_session_id:
            headers["X-Apple-ID-Session-Id"] = pending.apple_session_id
        if pending.scnt:
            headers["scnt"] = pending.scnt
    return headers


async def initiate_auth(email: str, password: str) -> dict[str, Any]:
    """Sign in to Apple and trigger 2FA.

    Args:
        email: Apple ID email address.
        password: Apple ID password (the account password — NOT an app-specific one).

    Returns:
        ``{"session_id": "...", "requires_2fa": True}``.

    Raises:
        IcloudAuthPasswordError: Apple rejected the email/password.
        IcloudAuthError: any other upstream/network failure.
    """
    _gc()
    session = aiohttp.ClientSession()
    pending = _PendingAuth(email=email, password=password, session=session)
    try:
        async with session.post(
            f"{_AUTH_ENDPOINT}/signin",
            params={"isRememberMeEnabled": "true"},
            json={"accountName": email, "password": password, "rememberMe": True, "trustTokens": []},
            headers=_auth_headers(),
        ) as resp:
            if resp.status in (401, 403):
                raise IcloudAuthPasswordError("Apple rejected that Apple ID and password.")
            if resp.status != 409:  # 409 = 2FA required, the expected path
                body = await resp.text()
                raise IcloudAuthError(f"Apple sign-in failed (HTTP {resp.status}): {body[:200]}")
            pending.scnt = resp.headers.get("scnt")
            pending.apple_session_id = resp.headers.get("X-Apple-ID-Session-Id")

        # Ask Apple to push a 2FA code to the trusted devices.
        async with session.put(
            f"{_AUTH_ENDPOINT}/verify/trusteddevice",
            headers=_auth_headers(pending),
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise IcloudAuthError(f"Couldn't send the 2FA code (HTTP {resp.status}): {body[:200]}")
    except IcloudAuthError:
        await session.close()
        raise
    except aiohttp.ClientError as exc:
        await session.close()
        raise IcloudAuthError(f"Network error talking to Apple: {exc}") from exc

    session_id = secrets.token_hex(32)
    _pending[session_id] = pending
    return {"session_id": session_id, "requires_2fa": True}


async def complete_auth(session_id: str, code: str) -> dict[str, Any]:
    """Validate the 2FA code and return the long-lived trust token.

    Args:
        session_id: The id returned by :func:`initiate_auth`.
        code: The 6-digit code from the user's Apple device.

    Returns:
        ``{"trust_token": "..."}``.

    Raises:
        IcloudAuthError: invalid/expired code or session, or upstream failure.
    """
    _gc()
    pending = _pending.get(session_id)
    if pending is None or pending.expired:
        _pending.pop(session_id, None)
        raise IcloudAuthError("That sign-in session expired. Please start over.")

    session = pending.session
    try:
        async with session.post(
            f"{_AUTH_ENDPOINT}/verify/trusteddevice/securitycode",
            json={"securityCode": {"code": code}},
            headers=_auth_headers(pending),
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise IcloudAuthError(f"That 2FA code wasn't accepted (HTTP {resp.status}): {body[:200]}")

        async with session.get(
            f"{_AUTH_ENDPOINT}/2sv/trust",
            headers=_auth_headers(pending),
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise IcloudAuthError(f"Couldn't trust the session (HTTP {resp.status}): {body[:200]}")
            trust_token = resp.headers.get("X-Apple-TwoSV-Trust-Token", "")

        if not trust_token:
            # Some accounts return the token only via the setup endpoint.
            async with session.post(
                f"{_SETUP_ENDPOINT}/accountLogin",
                json={
                    "accountCountryCode": "",
                    "dsWebAuthToken": pending.apple_session_id or "",
                    "extended_login": True,
                    "trustToken": "",
                },
            ) as resp:
                if resp.status < 400:
                    data = await resp.json()
                    trust_token = data.get("trust_token") or resp.headers.get("X-Apple-TwoSV-Trust-Token", "")

        if not trust_token:
            raise IcloudAuthError("Apple didn't return a trust token — the sign-in may not have completed.")
    except IcloudAuthError:
        raise
    except aiohttp.ClientError as exc:
        raise IcloudAuthError(f"Network error talking to Apple: {exc}") from exc
    finally:
        _pending.pop(session_id, None)
        await session.close()

    return {"trust_token": trust_token}
