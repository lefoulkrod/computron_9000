"""Per-slug catalog used to spawn the broker for each integration.

A minimal in-Python table for now — later this loads from
``config/integrations_catalog/*.json`` at supervisor startup. Tests inject a
custom catalog so they can point broker spawn commands at the ``fake_email``
fixture's random ports.

One broker process per integration: whether the integration serves email,
calendar, both, or an MCP server, it's a single subprocess with one UDS
socket. See the ``CatalogEntry`` fields below for the spawn surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CatalogEntry:
    """Per-slug description of how to spawn the broker for an integration."""

    slug: str
    """Identifier matching the ``slug`` in ``<id>.meta`` files and in user-facing
    catalog pickers (e.g. ``"icloud"``, ``"gmail"``, ``"github"``)."""

    command: list[str]
    """The argv to exec for the broker subprocess
    (e.g. ``["python", "-m", "integrations.brokers.email_broker"]``)."""

    capabilities: frozenset[str] = frozenset()
    """Tags the app server uses to decide which agent tools to expose for this
    integration. Each capability corresponds to a family of tools — e.g.
    ``"email"`` unlocks the IMAP-backed email tools; ``"calendar"`` unlocks
    CalDAV tools when those land. The supervisor surfaces these in ``list``
    and ``add`` RPC responses so the app server doesn't need to know which
    slug supports which tools."""

    static_env: dict[str, str] = field(default_factory=dict)
    """Env vars the supervisor provides directly — protocol hosts, ports, etc.
    Not derived from the user's credential blob."""

    env_injection: dict[str, str] = field(default_factory=dict)
    """Maps secret-bundle keys to env-var names. For example
    ``{"email": "EMAIL_USER", "password": "EMAIL_PASS"}`` means the supervisor
    reads ``email`` and ``password`` from the decrypted bundle and sets the
    corresponding env vars when it spawns the broker for this slug."""


_ICLOUD = CatalogEntry(
    slug="icloud",
    command=["python", "-m", "integrations.brokers.email_broker"],
    capabilities=frozenset({"email"}),
    static_env={
        "IMAP_HOST": "imap.mail.me.com",
        "IMAP_PORT": "993",
        "SMTP_HOST": "smtp.mail.me.com",
        "SMTP_PORT": "587",
    },
    env_injection={
        "email": "EMAIL_USER",
        "password": "EMAIL_PASS",
    },
)


_GMAIL = CatalogEntry(
    slug="gmail",
    command=["python", "-m", "integrations.brokers.email_broker"],
    capabilities=frozenset({"email"}),
    static_env={
        "IMAP_HOST": "imap.gmail.com",
        "IMAP_PORT": "993",
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_PORT": "587",
    },
    env_injection={
        "email": "EMAIL_USER",
        "password": "EMAIL_PASS",
    },
)


DEFAULT_CATALOG: dict[str, CatalogEntry] = {
    "icloud": _ICLOUD,
    "gmail": _GMAIL,
}
