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
class BrokerSpec:
    """How to spawn one broker subprocess for a capability."""

    capability: str
    command: list[str]
    static_env: dict[str, str] = field(default_factory=dict)
    env_injection: dict[str, str] = field(default_factory=dict)
    host_paths: tuple[HostPathBinding, ...] = ()


@dataclass(frozen=True)
class CatalogEntry:
    """Per-slug description of how to spawn the broker for an integration."""

    slug: str
    """Identifier matching the ``slug`` in ``<id>.meta`` files and in user-facing
    catalog pickers (e.g. ``"icloud"``, ``"gmail"``, ``"github"``)."""

    label: str
    """Human-readable label for this integration (e.g. ``"iCloud"``, ``"Google"``)."""

    brokers: tuple[BrokerSpec, ...]
    """One or more broker specs, each corresponding to a capability. A single
    catalog entry can spawn multiple brokers (e.g. email_broker + rclone_broker)
    sharing the same credential bundle."""

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset(b.capability for b in self.brokers)

    def broker_for(self, capability: str) -> BrokerSpec:
        for b in self.brokers:
            if b.capability == capability:
                return b
        raise KeyError(capability)


_EMAIL_HOST_PATHS = (
    # Email attachments land in the shared "downloads" role alongside browser
    # saves: both are agent-initiated retrievals from outside the container.
    HostPathBinding(role="downloads", env_var="ATTACHMENTS_DIR", mode="write"),
)

_RCLONE_HOST_PATHS = (
    HostPathBinding(role="downloads", env_var="DOWNLOADS_DIR", mode="write"),
)


_ICLOUD = CatalogEntry(
    slug="icloud",
    label="iCloud",
    brokers=(
        BrokerSpec(
            capability="email_calendar",
            command=["python", "-m", "integrations.brokers.email_broker"],
            static_env={
                "IMAP_HOST": "imap.mail.me.com",
                "IMAP_PORT": "993",
                "SMTP_HOST": "smtp.mail.me.com",
                "SMTP_PORT": "587",
                "CALDAV_URL": "https://caldav.icloud.com",
            },
            env_injection={"email": "EMAIL_USER", "password": "EMAIL_PASS"},
            host_paths=_EMAIL_HOST_PATHS,
        ),
    ),
)


_ICLOUD_DRIVE = CatalogEntry(
    slug="icloud_drive",
    label="iCloud Drive",
    brokers=(
        BrokerSpec(
            capability="storage",
            command=["python", "-m", "integrations.brokers.rclone_broker"],
            static_env={},
            env_injection={"email": "RCLONE_CONFIG_DEFAULT_USER"},
            host_paths=_RCLONE_HOST_PATHS,
        ),
    ),
)


_GMAIL = CatalogEntry(
    slug="gmail",
    label="Google",
    brokers=(
        BrokerSpec(
            capability="email_calendar",
            command=["python", "-m", "integrations.brokers.email_broker"],
            static_env={
                "IMAP_HOST": "imap.gmail.com",
                "IMAP_PORT": "993",
                "SMTP_HOST": "smtp.gmail.com",
                "SMTP_PORT": "587",
            },
            env_injection={"email": "EMAIL_USER", "password": "EMAIL_PASS"},
            host_paths=_EMAIL_HOST_PATHS,
        ),
    ),
)


DEFAULT_CATALOG: dict[str, CatalogEntry] = {
    "icloud": _ICLOUD,
    "icloud_drive": _ICLOUD_DRIVE,
    "gmail": _GMAIL,
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
        for spec in entry.brokers:
            for binding in spec.host_paths:
                if binding.role not in host_paths:
                    msg = (
                        f"catalog entry {slug!r} capability {spec.capability!r} "
                        f"binds host-path role {binding.role!r} which is not in the registry"
                    )
                    raise ValueError(msg)
