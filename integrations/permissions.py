"""Capability and access-level enums for the integrations permission model.

No internal dependencies — importable from any layer (supervisor, brokers,
tool gating, server routes).
"""

from __future__ import annotations

from enum import IntEnum, StrEnum


class Capability(StrEnum):
    """What an integration can do — each maps to a family of agent tools."""

    EMAIL = "email"
    CALENDAR = "calendar"
    DRIVE = "drive"
    CONTACTS = "contacts"


class Access(IntEnum):
    """How much access the user grants for one capability.

    IntEnum so comparisons work naturally: ``Access.READ_WRITE > Access.READ``.
    Serialized to/from short strings at wire boundaries (meta JSON, env vars,
    RPC frames) via :func:`access_to_str` / :func:`access_from_str`.
    """

    OFF = 0
    READ = 1
    READ_WRITE = 2


_ACCESS_TO_STR: dict[Access, str] = {
    Access.OFF: "off",
    Access.READ: "r",
    Access.READ_WRITE: "rw",
}

_STR_TO_ACCESS: dict[str, Access] = {v: k for k, v in _ACCESS_TO_STR.items()}


def access_to_str(access: Access) -> str:
    """Short string form for wire serialization: ``"off"``, ``"r"``, ``"rw"``."""
    return _ACCESS_TO_STR[access]


def access_from_str(s: str) -> Access:
    """Parse a short string back to an Access level. Raises ValueError on bad input."""
    result = _STR_TO_ACCESS.get(s)
    if result is None:
        msg = f"unknown access level: {s!r} (expected one of {sorted(_STR_TO_ACCESS)})"
        raise ValueError(msg)
    return result


Permissions = dict[Capability, Access]


def permissions_to_dict(perms: Permissions) -> dict[str, str]:
    """Serialize to a JSON-friendly ``{capability: access_str}`` dict."""
    return {cap.value: access_to_str(access) for cap, access in perms.items()}


def permissions_from_dict(d: dict[str, str]) -> Permissions:
    """Deserialize from a JSON ``{capability: access_str}`` dict.

    Skips unknown capabilities so a meta file written by a newer version
    (with capabilities this version doesn't know about) doesn't crash on
    load — the unknown capability is simply invisible until the code is
    updated.
    """
    perms: Permissions = {}
    for cap_str, access_str in d.items():
        try:
            cap = Capability(cap_str)
        except ValueError:
            continue
        perms[cap] = access_from_str(access_str)
    return perms


def permissions_to_env(perms: Permissions) -> str:
    """Encode as an env-var value: ``email:rw,calendar:r,...``."""
    return ",".join(
        f"{cap.value}:{access_to_str(access)}"
        for cap, access in sorted(perms.items(), key=lambda p: p[0].value)
    )


def permissions_from_env(s: str) -> Permissions:
    """Decode from env-var form. Empty string → empty dict."""
    if not s:
        return {}
    perms: Permissions = {}
    for pair in s.split(","):
        cap_str, _, access_str = pair.partition(":")
        try:
            cap = Capability(cap_str)
        except ValueError:
            continue
        perms[cap] = access_from_str(access_str)
    return perms
