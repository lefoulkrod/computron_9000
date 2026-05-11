"""iCloud Drive authentication — direct Apple API calls (no pyicloud).

Exposes a session-based API so the web UI can drive a two-step auth flow:

1. ``initiate_auth(email, password)`` → signin, triggers 2FA
2. ``complete_auth(session_id, code)`` → validates 2FA, returns trust_token

Sessions are held in-memory (single-user system — negligible footprint).
No filesystem writes — the trust_token is returned to the caller, which
passes it through the normal supervisor add flow as an env var.
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

# ── Apple endpoints ─────────────────────────────────────────────────────────

_AUTH_ENDPOINT = "https://idmsa.apple.com/appleauth/auth"
_SETUP_ENDPOINT = "https://setup.icloud.com/setup/ws/1"

# ── session store ──────────────────────────────────────────────────────────

_SESSION_TTL = 600  # 10 minutes


@dataclass
class _AuthSession:
    email: str
    password: str
    session: aiohttp.ClientSession
    scnt: str | None = None
    session_id: str | None = None
    created: float = field(default_factory=time.monotonic)

    @property
    def expired(self) -> bool:
        return (time.monotonic() - self.created) > _SESSION_TTL


_sessions: dict[str, _AuthSession] = {}


def _gc_sessions() -> None:
    """Drop expired sessions."""
    stale = [sid for sid, s in _sessions.items() if s.expired]
    for sid in stale:
        del _sessions[sid]


# ── public API ─────────────────────────────────────────────────────────────


class IcloudAuthError(Exception):
    """Auth flow failed for a reason the UI should surface."""


class IcloudAuthPasswordError(IcloudAuthError):
    """Apple rejected the password (wrong password or locked account)."""


async def initiate_auth(email: str, password: str) -> dict[str, Any]:
    """Sign in to Apple and trigger 2FA.

    Args:
        email: Apple ID email address.
        password: Apple ID password (NOT app-specific).

    Returns:
        ``{session_id, requires_2fa}``

    Raises:
        IcloudAuthPasswordError: Apple rejected the password.
        IcloudAuthError: Something else went wrong.
    """
    _gc_sessions()

    session = aiohttp.ClientSession()
    auth_session = _AuthSession(email=email, password=password, session=session)

    try:
        # Step 1: signin — POST email + password to Apple
        data = {
            "accountName": email,
            "password": password,
            "rememberMe": True,
            "trustTokens": [],
        }
        headers = _auth_headers()

        async with session.post(
            f"{_AUTH_ENDPOINT}/signin",
            params={"isRememberMeEnabled": "true"},
            json=data,
            headers=headers,
        ) as resp:
            if resp.status == 409:
                # 409 = 2FA required — expected
                pass
            elif resp.status == 401 or resp.status == 403:
                raise IcloudAuthPasswordError(
                    "Invalid email/password combination."
                )
            elif resp.status >= 400:
                body = await resp.text()
                raise IcloudAuthError(
                    f"Signin failed (HTTP {resp.status}): {body[:200]}"
                )

            # Capture scnt and session_id from response headers
            auth_session.scnt = resp.headers.get("scnt")
            auth_session.session_id = resp.headers.get("X-Apple-ID-Session-Id")

        # Step 2: trigger 2FA — send code to trusted device
        await _send_2fa_code(session, auth_session)

    except IcloudAuthError:
        await session.close()
        raise
    except aiohttp.ClientError as exc:
        await session.close()
        raise IcloudAuthError(f"Network error: {exc}") from exc

    session_id = secrets.token_hex(32)
    _sessions[session_id] = auth_session
    return {"session_id": session_id, "requires_2fa": True}


async def complete_auth(session_id: str, code: str) -> dict[str, Any]:
    """Validate the 2FA code and return the trust token.

    Args:
        session_id: From ``initiate_auth``.
        code: 6-digit 2FA code from the user's Apple device.

    Returns:
        ``{trust_token: "<token>"}``

    Raises:
        IcloudAuthError: Invalid code, expired session, or upstream failure.
    """
    _gc_sessions()

    auth_session = _sessions.get(session_id)
    if auth_session is None:
        raise IcloudAuthError("Session expired or not found. Please start over.")
    if auth_session.expired:
        del _sessions[session_id]
        raise IcloudAuthError("Session expired. Please start over.")

    session = auth_session.session

    try:
        # Step 3: validate 2FA code
        headers = _auth_headers()
        if auth_session.session_id:
            headers["X-Apple-ID-Session-Id"] = auth_session.session_id
        if auth_session.scnt:
            headers["scnt"] = auth_session.scnt

        async with session.post(
            f"{_AUTH_ENDPOINT}/verify/trusteddevice/securitycode",
            json={"securityCode": {"code": code}},
            headers=headers,
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise IcloudAuthError(
                    f"2FA verification failed (HTTP {resp.status}): {body[:200]}"
                )

        # Step 4: trust the session to get a trust token
        async with session.get(
            f"{_AUTH_ENDPOINT}/2sv/trust",
            headers=headers,
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise IcloudAuthError(
                    f"Trust session failed (HTTP {resp.status}): {body[:200]}"
                )

        # Step 5: authenticate with token to get the trust_token
        async with session.post(
            f"{_SETUP_ENDPOINT}/accountLogin",
            json={
                "accountCountryCode": "",
                "dsWebAuthToken": auth_session.session_id or "",
                "extended_login": True,
                "trustToken": "",
            },
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise IcloudAuthError(
                    f"Account login failed (HTTP {resp.status}): {body[:200]}"
                )
            data = await resp.json()

        trust_token = data.get("trust_token") or ""
        if not trust_token:
            # Try from headers
            trust_token = resp.headers.get("X-Apple-TwoSV-Trust-Token", "")

        if not trust_token:
            raise IcloudAuthError(
                "No trust token in response — auth may not have completed."
            )

    except IcloudAuthError:
        raise
    except aiohttp.ClientError as exc:
        raise IcloudAuthError(f"Network error: {exc}") from exc
    finally:
        _sessions.pop(session_id, None)
        await session.close()

    return {"trust_token": trust_token}


# ── helpers ────────────────────────────────────────────────────────────────


def _auth_headers() -> dict[str, str]:
    return {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "X-Apple-Widget-Key": "83545bf919730e51dbfba24e7e8a78d2",
        "X-Apple-I-FD-Client-Info": json.dumps({
            "U": "Mozilla/5.0",
            "L": "en-US",
            "Z": "GMT-05:00",
            "V": "1.1",
            "F": "",
        }),
    }


async def _send_2fa_code(
    session: aiohttp.ClientSession, auth_session: _AuthSession,
) -> None:
    """Trigger Apple to send a 2FA code to the first trusted device."""
    headers = _auth_headers()
    if auth_session.session_id:
        headers["X-Apple-ID-Session-Id"] = auth_session.session_id
    if auth_session.scnt:
        headers["scnt"] = auth_session.scnt

    async with session.put(
        f"{_AUTH_ENDPOINT}/verify/trusteddevice/securitycode",
        headers=headers,
    ) as resp:
        if resp.status >= 400:
            body = await resp.text()
            raise IcloudAuthError(
                f"Failed to send 2FA code (HTTP {resp.status}): {body[:200]}"
            )