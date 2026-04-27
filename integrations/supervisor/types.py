"""Pydantic models for the supervisor's on-disk and in-memory shapes.

Imports only stdlib and pydantic — no internal dependencies — so this module
can be imported from anywhere in the supervisor without introducing a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


@dataclass(frozen=True)
class HostPath:
    """A directory the supervisor will hand out to brokers that bind its role.

    The fields together record both the location and the permission posture
    the directory is supposed to have. ``container/entrypoint.sh`` is what
    actually enforces the posture (it runs as root before any process drops
    privilege); the values here are the canonical record of what the
    entrypoint should set, so changes happen in lockstep.
    """

    path: Path
    description: str
    owner: str
    group: str
    mode: int


@dataclass(frozen=True)
class HostPathBinding:
    """Catalog-side opt-in: this integration's broker wants ``role`` at ``env_var``.

    ``role`` names a key in the supervisor's host-path registry (validated at
    boot). ``env_var`` is the env-var name the broker subprocess expects the
    resolved path under. ``mode`` records whether the broker reads or writes
    — informational today, a hook for future enforcement.
    """

    role: str
    env_var: str
    mode: Literal["read", "write"]


class IntegrationMeta(BaseModel):
    """Non-secret metadata for one installed integration.

    Lives as plaintext JSON at ``<vault>/creds/<id>.meta`` next to the encrypted
    ``<id>.enc`` (which holds the secret bundle). Keeping the non-secret fields
    plaintext lets the supervisor list integrations, toggle permissions, and
    rebuild its registry on restart without touching the master key.

    Attributes:
        version: Schema version for forward-compat. Bump when field layout
            changes in a way that needs migration.
        id: Stable identity, formatted ``<slug>_<user_suffix>``, ``[a-z0-9_-]+``
            up to 64 chars. Not editable after creation.
        slug: Catalog entry slug (e.g. ``"gmail"``, ``"icloud"``). Selects the
            broker binary and any provider-specific config the catalog ships.
        label: Human-readable label shown in the UI. User-editable.
        write_allowed: Permission gate. When ``False`` the supervisor passes
            ``WRITE_ALLOWED=false`` into every broker it spawns for this
            integration, and the broker itself refuses write-classified verbs
            at dispatch. The flag is the real enforcement point: an agent
            bypassing the app server's tool registry and connecting directly
            to a broker's UDS still gets refused by the broker itself.
        added_at: When the integration was first added.
        updated_at: Last time the metadata or the encrypted blob was rewritten.
    """

    version: int = 1
    id: str
    slug: str
    label: str
    write_allowed: bool = False
    added_at: datetime
    updated_at: datetime
