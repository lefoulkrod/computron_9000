"""iCloud Drive pre-authentication — Apple ID web sign-in (SRP-6a) + 2FA.

Apple's web sign-in moved off the legacy plaintext-password endpoint, so the
flow is now a three-step exchange against ``idmsa.apple.com/appleauth/auth``:

1. ``/signin/init`` — client sends its SRP public ``A`` and the account name;
   Apple replies with the SRP salt, iteration count, server public ``B``,
   a challenge id, and which protocol variant to use (``s2k`` or ``s2k_fo``).
2. SRP-6a math — derive the session key, compute proofs ``M1`` / ``M2``.
3. ``/signin/complete`` — submit ``M1`` / ``M2`` plus the challenge id; Apple
   replies 409 to indicate 2FA is required, captures ``scnt`` and
   ``X-Apple-ID-Session-Id`` for the rest of the flow.

After that, the trusted-device dance is the same on both legacy and SRP
endpoints: PUT to push a code to the trusted devices, POST the 6-digit code
back, and GET ``/2sv/trust`` to receive the long-lived trust token.

The trust token (plus the Apple ID and password) gets injected into rclone's
``RCLONE_CONFIG_DEFAULT_*`` env vars by the supervisor so the broker can talk
to iCloud Drive without re-doing 2FA on every spawn.

Pending sessions are held in process memory only — a restart drops them and
the user starts over. Single-user system, so the footprint is negligible.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
import uuid
from base64 import b64decode, b64encode
from dataclasses import dataclass, field
from typing import Any, Literal

import aiohttp

logger = logging.getLogger(__name__)

_AUTH_ENDPOINT = "https://idmsa.apple.com/appleauth/auth"
_SETUP_ENDPOINT = "https://setup.icloud.com/setup/ws/1"

# The iCloud web client's public widget key — same value Apple's own
# www.icloud.com first-party UI presents. Identifies the OAuth client to
# Apple's auth surface; not a secret.
_ICLOUD_WIDGET_KEY = "d39ba9916b7251055b22c7f910e2ea796ee65e98b2ddecea8f5dde8d9d1a815d"
_ICLOUD_REDIRECT_URI = "https://www.icloud.com"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Safari/605.1.15"
)

_SESSION_TTL_SECONDS = 600.0


# ── SRP-6a parameters (RFC 5054 group 2048, Apple's variant) ────────────────

# RFC 5054 §A.2 2048-bit safe prime.
_N_HEX = (
    "AC6BDB41324A9A9BF166DE5E1389582FAF72B6651987EE07FC3192943DB56050"
    "A37329CBB4A099ED8193E0757767A13DD52312AB4B03310DCD7F48A9DA04FD50"
    "E8083969EDB767B0CF6095179A163AB3661A05FBD5FAAAE82918A9962F0B93B8"
    "55F97993EC975EEAA80D740ADBF4FF74"
    "7359D041D5C33EA71D281E446B14773BCA97B43A23FB801676BD207A436C6481"
    "F1D2B9078717461A5B9D32E688F87748544523B524B0D57D5EA77A2775D2ECFA"
    "032CFBDBF52FB3786160279004E57AE6AF874E7303CE5329"
    "9CCC041C7BC308D82A5698F3A8D0C38271AE35F8E9DBFBB694B5C803D89F7AE4"
    "35DE236D525F54759B65E372FCD68EF20FA7111F9E4AFF73"
)
_N = int(_N_HEX, 16)
_G = 2
_N_BYTES = (_N.bit_length() + 7) // 8  # 256


def _h(*chunks: bytes) -> bytes:
    """SHA-256 over the concatenation of ``chunks``."""
    sha = hashlib.sha256()
    for c in chunks:
        sha.update(c)
    return sha.digest()


def _i2b(value: int, length: int | None = None) -> bytes:
    """Big-endian byte encoding of ``value``, optionally zero-padded to ``length``."""
    if length is None:
        length = max(1, (value.bit_length() + 7) // 8)
    return value.to_bytes(length, "big")


def _b2i(blob: bytes) -> int:
    return int.from_bytes(blob, "big")


def _srp_k() -> int:
    """SRP multiplier ``k = H(N || PAD(g))``."""
    return _b2i(_h(_i2b(_N), _i2b(_G, _N_BYTES)))


_K = _srp_k()


def _srp_x(salt: bytes, password: str, iteration: int, protocol: str) -> int:
    """Apple's password-derived ``x``.

    Apple always pre-hashes the password with SHA-256 before PBKDF2: for
    ``s2k`` the raw 32-byte digest, for ``s2k_fo`` the hex-encoded form. The
    resulting bytes stand in for the password in the standard RFC 5054
    derivation, which Apple uses with the identity omitted:

        x = H(salt || H(":" || pbkdf2_output))

    The leading colon stays even when the identity is empty — RFC 5054
    keeps the ``I:p`` separator, and Apple's server expects it.
    """
    pw_hash = _h(password.encode("utf-8"))
    pw_input = pw_hash.hex().encode("ascii") if protocol == "s2k_fo" else pw_hash
    pbkdf = hashlib.pbkdf2_hmac("sha256", pw_input, salt, iteration, dklen=32)
    inner = _h(b":", pbkdf)
    return _b2i(_h(salt, inner))


def _srp_proofs(
    a: int, big_a: int, big_b: int, x: int, salt: bytes, username: str,
) -> tuple[bytes, bytes, bytes]:
    """Compute ``M1``, ``M2``, and the session key ``K`` for SRP-6a.

    Standard SRP-6a per RFC 5054 §2.6:
      u = H(PAD(A) || PAD(B))
      S = (B - k * g^x) ^ (a + u * x) mod N
      K = H(S)
      M1 = H(H(N) XOR H(g) || H(I) || s || PAD(A) || PAD(B) || K)
      M2 = H(PAD(A) || M1 || K)
    """
    # u uses A and B PADDED to N's byte length (RFC 5054 §2.6).
    u = _b2i(_h(_i2b(big_a, _N_BYTES), _i2b(big_b, _N_BYTES)))
    s = pow((big_b - _K * pow(_G, x, _N)) % _N, a + u * x, _N)
    # K and the M-proofs hash A, B, S WITHOUT padding — pysrp's rfc5054
    # mode pads only inside H()'s width=… form, and the proof formulas
    # don't go through that path.
    session_key = _h(_i2b(s))
    h_n = _h(_i2b(_N))
    h_g = _h(_i2b(_G, _N_BYTES))
    h_xor = bytes(a_ ^ b_ for a_, b_ in zip(h_n, h_g, strict=True))
    h_user = _h(username.encode("utf-8"))
    m1 = _h(h_xor, h_user, salt, _i2b(big_a), _i2b(big_b), session_key)
    m2 = _h(_i2b(big_a), m1, session_key)
    return m1, m2, session_key


# ── session store ──────────────────────────────────────────────────────────


@dataclass
class _PendingAuth:
    email: str
    password: str
    session: aiohttp.ClientSession
    client_id: str
    scnt: str | None = None
    apple_session_id: str | None = None
    session_key: bytes | None = None
    created: float = field(default_factory=time.monotonic)

    @property
    def expired(self) -> bool:
        return (time.monotonic() - self.created) > _SESSION_TTL_SECONDS


_pending: dict[str, _PendingAuth] = {}


def _gc() -> None:
    """Drop expired sessions; close their HTTP sessions best-effort."""
    for sid in [sid for sid, p in _pending.items() if p.expired]:
        stale = _pending.pop(sid, None)
        if stale is not None:
            stale.session.detach()


class IcloudAuthError(Exception):
    """The sign-in flow failed for a reason worth surfacing to the user."""


class IcloudAuthPasswordError(IcloudAuthError):
    """Apple rejected the Apple ID / password pair."""


def _auth_headers(client_id: str, pending: _PendingAuth | None = None) -> dict[str, str]:
    """Headers Apple's first-party iCloud web client sends on auth requests.

    Apple's auth surface scopes OAuth state by the client id / widget key
    combo plus the redirect URI. ``client_id`` is a per-session UUID that
    Apple echoes back; it ties the init exchange to the complete call.
    """
    headers = {
        "Accept": "application/json, text/javascript",
        "Content-Type": "application/json",
        "User-Agent": _USER_AGENT,
        "Origin": _ICLOUD_REDIRECT_URI,
        "Referer": f"{_ICLOUD_REDIRECT_URI}/",
        "X-Apple-Widget-Key": _ICLOUD_WIDGET_KEY,
        "X-Apple-OAuth-Client-Id": _ICLOUD_WIDGET_KEY,
        "X-Apple-OAuth-Client-Type": "firstPartyAuth",
        "X-Apple-OAuth-Redirect-URI": _ICLOUD_REDIRECT_URI,
        "X-Apple-OAuth-Require-Grant-Code": "true",
        "X-Apple-OAuth-Response-Mode": "web_message",
        "X-Apple-OAuth-Response-Type": "code",
        "X-Apple-OAuth-State": client_id,
        "X-Apple-I-FD-Client-Info": json.dumps(
            {"U": _USER_AGENT, "L": "en-US", "Z": "GMT+00:00", "V": "1.1", "F": ""},
        ),
    }
    if pending is not None:
        if pending.apple_session_id:
            headers["X-Apple-ID-Session-Id"] = pending.apple_session_id
        if pending.scnt:
            headers["scnt"] = pending.scnt
    return headers


def _new_client_id() -> str:
    return f"auth-{uuid.uuid4()}".lower()


async def _srp_signin(
    session: aiohttp.ClientSession,
    email: str,
    password: str,
    client_id: str,
) -> tuple[str | None, str | None, bytes, Literal[200, 409]]:
    """Run the two-step SRP-6a exchange against Apple's signin endpoint.

    Returns ``(scnt, session_id, session_key, status)`` on success. ``status``
    is 200 for an account without 2FA (rare) and 409 for the normal 2FA path.

    Raises :class:`IcloudAuthPasswordError` on credential rejection,
    :class:`IcloudAuthError` for any other upstream/protocol failure.
    """
    # Step 1: /signin/init — send public A, receive salt + iteration + B.
    a = _b2i(secrets.token_bytes(32)) % _N
    big_a = pow(_G, a, _N)
    init_body = {
        # pysrp sends A as long_to_bytes(A) — minimum bytes, no zero-padding.
        # Apple's server reads it back as an int either way, but matching the
        # canonical encoding keeps things consistent across the flow.
        "a": b64encode(_i2b(big_a)).decode("ascii"),
        "accountName": email,
        "protocols": ["s2k", "s2k_fo"],
    }
    async with session.post(
        f"{_AUTH_ENDPOINT}/signin/init",
        json=init_body,
        headers=_auth_headers(client_id),
    ) as resp:
        text = await resp.text()
        if resp.status != 200:
            logger.warning("Apple /signin/init returned HTTP %d: %s", resp.status, text[:300])
            if resp.status in (401, 403):
                raise IcloudAuthPasswordError("Apple didn't recognize that Apple ID.")
            raise IcloudAuthError(f"Apple sign-in init failed (HTTP {resp.status}).")
        try:
            init = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("Apple /signin/init returned non-JSON body: %s", text[:300])
            raise IcloudAuthError("Apple sign-in init returned an unexpected response.") from exc

    salt = b64decode(init["salt"])
    iteration = int(init["iteration"])
    protocol = str(init["protocol"])
    big_b = _b2i(b64decode(init["b"]))
    challenge_id = init["c"]
    logger.info(
        "Apple /signin/init OK: protocol=%s iteration=%d salt_len=%d b_len=%d",
        protocol, iteration, len(salt), (big_b.bit_length() + 7) // 8,
    )
    if protocol not in ("s2k", "s2k_fo"):
        logger.warning("Apple proposed unknown SRP protocol %r", protocol)
        raise IcloudAuthError(f"Apple wants an SRP variant we don't speak: {protocol}.")

    # Step 2: derive proofs.
    x = _srp_x(salt, password, iteration, protocol)
    m1, m2, session_key = _srp_proofs(a, big_a, big_b, x, salt, email)

    # Step 3: /signin/complete — submit M1 and M2. 409 means 2FA needed.
    complete_body = {
        "accountName": email,
        "c": challenge_id,
        "m1": b64encode(m1).decode("ascii"),
        "m2": b64encode(m2).decode("ascii"),
        "rememberMe": True,
        "trustTokens": [],
    }
    async with session.post(
        f"{_AUTH_ENDPOINT}/signin/complete",
        params={"isRememberMeEnabled": "true"},
        json=complete_body,
        headers=_auth_headers(client_id),
    ) as resp:
        body = await resp.text()
        if resp.status in (401, 403):
            logger.warning(
                "Apple /signin/complete rejected (HTTP %d): %s",
                resp.status, body[:500],
            )
            raise IcloudAuthPasswordError("Apple rejected that Apple ID and password.")
        if resp.status not in (200, 409):
            logger.warning(
                "Apple /signin/complete returned HTTP %d: %s",
                resp.status, body[:500],
            )
            raise IcloudAuthError(f"Apple sign-in complete failed (HTTP {resp.status}).")
        scnt = resp.headers.get("scnt")
        apple_session_id = resp.headers.get("X-Apple-ID-Session-Id")
        if resp.status == 200:
            logger.info("Apple signed in without 2FA (account has it disabled or already trusted)")
        status: Literal[200, 409] = 409 if resp.status == 409 else 200
    return scnt, apple_session_id, session_key, status


# ── public API ─────────────────────────────────────────────────────────────


async def initiate_auth(email: str, password: str) -> dict[str, Any]:
    """Sign in to Apple via SRP-6a, then trigger 2FA.

    Args:
        email: Apple ID email address.
        password: Apple ID account password (not an app-specific one).

    Returns:
        ``{"session_id": "...", "requires_2fa": True}``.

    Raises:
        IcloudAuthPasswordError: Apple rejected the credentials.
        IcloudAuthError: any other upstream / network / protocol failure.
    """
    _gc()
    session = aiohttp.ClientSession()
    client_id = _new_client_id()
    pending = _PendingAuth(
        email=email, password=password, session=session, client_id=client_id,
    )
    try:
        scnt, apple_sid, session_key, status = await _srp_signin(
            session, email, password, client_id,
        )
        pending.scnt = scnt
        pending.apple_session_id = apple_sid
        pending.session_key = session_key

        if status == 200:
            # 2FA disabled on the account — extremely rare for iCloud Drive
            # accounts, but if it happens the caller still expects to get a
            # trust token via the complete_auth path. We can't proceed
            # without 2FA in this flow; surface clearly.
            raise IcloudAuthError(
                "This Apple ID doesn't have two-factor authentication enabled. "
                "Enable 2FA in your Apple ID settings and try again.",
            )
        # status == 409 means 2FA is required AND Apple has already pushed
        # the code to the trusted devices as part of the response — no
        # separate "trigger" call is needed.
    except IcloudAuthError:
        await session.close()
        raise
    except aiohttp.ClientError as exc:
        logger.warning("Network error talking to Apple during init: %s", exc)
        await session.close()
        raise IcloudAuthError(f"Network error talking to Apple: {exc}") from exc

    session_id = secrets.token_hex(32)
    _pending[session_id] = pending
    logger.info("iCloud signin pending for %s (session %s…)", email, session_id[:8])
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
            headers=_auth_headers(pending.client_id, pending),
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                logger.info(
                    "Apple /verify/securitycode returned HTTP %d: %s",
                    resp.status, body[:300],
                )
                raise IcloudAuthError(
                    f"That 2FA code wasn't accepted (HTTP {resp.status}).",
                )

        async with session.get(
            f"{_AUTH_ENDPOINT}/2sv/trust",
            headers=_auth_headers(pending.client_id, pending),
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                logger.warning(
                    "Apple /2sv/trust returned HTTP %d: %s",
                    resp.status, body[:300],
                )
                raise IcloudAuthError(
                    f"Couldn't trust the session (HTTP {resp.status}).",
                )
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
                    try:
                        data = await resp.json()
                    except aiohttp.ContentTypeError:
                        data = {}
                    trust_token = (
                        data.get("trust_token")
                        or resp.headers.get("X-Apple-TwoSV-Trust-Token", "")
                    )

        if not trust_token:
            raise IcloudAuthError(
                "Apple didn't return a trust token — the sign-in may not have completed.",
            )
    except IcloudAuthError:
        raise
    except aiohttp.ClientError as exc:
        logger.warning("Network error talking to Apple during verify: %s", exc)
        raise IcloudAuthError(f"Network error talking to Apple: {exc}") from exc
    finally:
        _pending.pop(session_id, None)
        await session.close()

    logger.info("iCloud trust token obtained (session %s…)", session_id[:8])
    return {"trust_token": trust_token}
