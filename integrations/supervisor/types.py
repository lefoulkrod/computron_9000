"""Pydantic models for the supervisor's on-disk and in-memory shapes.

Imports only stdlib and pydantic — no internal dependencies — so this module
can be imported from anywhere in the supervisor without introducing a cycle.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


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
