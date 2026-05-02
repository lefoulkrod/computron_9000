"""iCloud Drive authentication — SRP + 2FA via pyicloud.

Exposes a session-based API so the web UI can drive a two-step auth flow:

1. ``initiate_auth(email, password)`` → SRP handshake, triggers 2FA
2. ``complete_auth(session_id, code)`` → validates 2FA, writes rclone config

Sessions are held in-memory (single-user system — negligible footprint).
"""

from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyicloud import PyiCloudService
from pyicloud.exceptions import (
    PyiCloud2FARequiredException,
    PyiCloudAPIResponseException,
    PyiCloudFailedLoginException,
)

logger = logging.getLogger(__name__)

# ── session store ──────────────────────────────────────────────────────────

# Sessions expire after 10 minutes — the user has that long to enter the 2FA
# code before they need to restart.
_SESSION_TTL = 600


@dataclass
class _AuthSession:
    api: PyiCloudService
    email: str
    created: float = field(default_factory=time.monotonic)

    @property
    def expired(self) -> bool:
        return (time.monotonic() - self.created) > _SESSION_TTL


_sessions: dict[str, _AuthSession] = {}


def _gc_sessions() -> None:
    """Drop expired sessions."""
    stale = [sid for sid, s in _sessions.items() if s.expired]
    for sid in stale:
        try:
            _sessions[sid].api.logout()
        except Exception:
            pass
        del _sessions[sid]


# ── public API ─────────────────────────────────────────────────────────────


class IcloudAuthError(Exception):
    """Auth flow failed for a reason the UI should surface."""


class IcloudAuthPasswordError(IcloudAuthError):
    """Apple rejected the password (wrong password or locked account)."""


def initiate_auth(email: str, password: str) -> dict[str, Any]:
    """Start SRP handshake with Apple and trigger 2FA.

    Args:
        email: Apple ID email address.
        password: Apple ID password (NOT app-specific).

    Returns:
        ``{session_id, requires_2fa}`` — ``requires_2fa`` is always True
        in practice (new sessions always need 2FA for iCloud Drive).

    Raises:
        IcloudAuthPasswordError: Apple rejected the password.
        IcloudAuthError: Something else went wrong.
    """
    _gc_sessions()

    try:
        api = PyiCloudService(email, password)
    except PyiCloudFailedLoginException as exc:
        raise IcloudAuthPasswordError(f"Apple rejected the password: {exc}") from exc
    except Exception as exc:
        raise IcloudAuthError(f"Auth initiation failed: {exc}") from exc

    if not api.requires_2fa and not api.requires_2sa:
        # Trusted session already exists — rare on first auth but possible
        # if cookies were carried over.  Extract the token directly.
        session_id = _store_session(api, email)
        _write_rclone_config(email, api)
        return {"session_id": session_id, "requires_2fa": False}

    # Trigger 2FA — send code to the first trusted device
    if api.trusted_devices:
        try:
            api.send_verification_code(api.trusted_devices[0])
        except Exception as exc:
            raise IcloudAuthError(f"Failed to send 2FA code: {exc}") from exc
    else:
        # SMS fallback — the user can request this via the UI if needed
        pass

    session_id = _store_session(api, email)
    return {"session_id": session_id, "requires_2fa": True}


def complete_auth(session_id: str, code: str) -> dict[str, Any]:
    """Validate the 2FA code and write the rclone config.

    Args:
        session_id: From ``initiate_auth``.
        code: 6-digit 2FA code from the user's Apple device.

    Returns:
        ``{ok: true}``

    Raises:
        IcloudAuthError: Invalid code, expired session, or config write failed.
    """
    _gc_sessions()

    session = _sessions.get(session_id)
    if session is None:
        raise IcloudAuthError("Session expired or not found. Please start over.")
    if session.expired:
        del _sessions[session_id]
        raise IcloudAuthError("Session expired. Please start over.")

    try:
        if not session.api.validate_2fa_code(code):
            raise IcloudAuthError("Invalid 2FA code. Please try again.")
    except PyiCloudAPIResponseException as exc:
        raise IcloudAuthError(f"2FA verification failed: {exc}") from exc
    except Exception as exc:
        raise IcloudAuthError(f"2FA verification error: {exc}") from exc

    if session.api.requires_2sa:
        raise IcloudAuthError("2FA verification did not complete. Please try again.")

    # Write the rclone config so the broker can use it
    try:
        _write_rclone_config(session.email, session.api)
    except Exception as exc:
        raise IcloudAuthError(f"Failed to write rclone config: {exc}") from exc

    # Clean up
    del _sessions[session_id]

    return {"ok": True}


# ── helpers ────────────────────────────────────────────────────────────────


def _store_session(api: PyiCloudService, email: str) -> str:
    session_id = secrets.token_hex(32)
    _sessions[session_id] = _AuthSession(api=api, email=email)
    return session_id


def _write_rclone_config(email: str, api: PyiCloudService) -> None:
    """Write (or overwrite) the rclone config with the trust token from pyicloud."""
    trust_token = api.session.data.get("trust_token", "")
    if not trust_token:
        raise IcloudAuthError("No trust token in session — auth may not have completed.")

    config_dir = Path.home() / ".config" / "rclone"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "rclone.conf"

    # rclone INI format
    config_content = (
        "[default]\n"
        "type = iclouddrive\n"
        f"apple_id = {email}\n"
        f"trust_token = {trust_token}\n"
    )

    config_path.write_text(config_content, encoding="utf-8")
    config_path.chmod(0o600)
    logger.info("rclone config written to %s", config_path)
