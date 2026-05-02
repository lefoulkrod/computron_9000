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

from integrations.supervisor.types import HostPath, HostPathBinding


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

    host_paths: tuple[HostPathBinding, ...] = ()
    """Shared directories on the container filesystem this integration's broker
    consumes. Each binding names a role in the supervisor's host-path registry,
    the env var the broker subprocess expects, and the access mode (read or
    write). Empty for integrations that don't touch shared state — the MCP
    broker, for example."""


_EMAIL_HOST_PATHS = (
    # Email attachments land in the shared "downloads" role alongside browser
    # saves: both are agent-initiated retrievals from outside the container.
    HostPathBinding(role="downloads", env_var="ATTACHMENTS_DIR", mode="write"),
)


_ICLOUD = CatalogEntry(
    slug="icloud",
    command=["python", "-m", "integrations.brokers.email_broker"],
    capabilities=frozenset({"email", "calendar"}),
    static_env={
        "IMAP_HOST": "imap.mail.me.com",
        "IMAP_PORT": "993",
        "SMTP_HOST": "smtp.mail.me.com",
        "SMTP_PORT": "587",
        # CalDAV root — broker resolves the user's principal from here.
        # Same app-specific password authenticates IMAP and CalDAV.
        "CALDAV_URL": "https://caldav.icloud.com",
    },
    env_injection={
        "email": "EMAIL_USER",
        "password": "EMAIL_PASS",
    },
    host_paths=_EMAIL_HOST_PATHS,
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
    host_paths=_EMAIL_HOST_PATHS,
)


_GOOGLE_WORKSPACE = CatalogEntry(
    slug="google_workspace",
    command=["python", "-m", "integrations.brokers.google_workspace_broker"],
    # Capabilities are determined per-integration from the OAuth scopes the
    # user granted at consent time, not statically from the catalog. Phase
    # 1 leaves the static set empty — Phase 2 will surface the granted scopes
    # via the IntegrationMeta and the agent tool registry will read from there.
    capabilities=frozenset(),
    # No static_env: every Google API endpoint the broker hits is hard-coded
    # in the client modules (oauth2.googleapis.com, gmail.googleapis.com,
    # etc.). User-supplied client credentials live in the encrypted blob.
    static_env={},
    env_injection={
        "client_id": "OAUTH_CLIENT_ID",
        "client_secret": "OAUTH_CLIENT_SECRET",
        "access_token": "OAUTH_ACCESS_TOKEN",
        "refresh_token": "OAUTH_REFRESH_TOKEN",
        "token_uri": "OAUTH_TOKEN_URI",
        "scopes": "OAUTH_SCOPES",
        "expires_at": "OAUTH_EXPIRES_AT",
    },
    # No host-path bindings yet. Phase 4 (writes) may need a downloads
    # binding for Drive file uploads — defer until then.
    host_paths=(),
)


DEFAULT_CATALOG: dict[str, CatalogEntry] = {
    "icloud": _ICLOUD,
    "gmail": _GMAIL,
    "google_workspace": _GOOGLE_WORKSPACE,
}


def validate_host_path_bindings(
    catalog: dict[str, CatalogEntry],
    host_paths: dict[str, HostPath],
) -> None:
    """Fail fast if any catalog entry references a role the registry doesn't define.

    Run once at supervisor startup so a typo in a catalog entry's
    ``host_paths`` trips the boot rather than the first user trying to add
    an integration. The spawn path checks the same condition defensively —
    this is just for clearer failure timing.
    """
    for slug, entry in catalog.items():
        for binding in entry.host_paths:
            if binding.role not in host_paths:
                msg = (
                    f"catalog entry {slug!r} binds host-path role "
                    f"{binding.role!r} which is not in the registry"
                )
                raise ValueError(msg)
