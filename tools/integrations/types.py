"""Typed records the app server keeps about registered integrations.

The fields here are the subset of supervisor-side metadata that crosses the
public RPC and that the app actually uses (tool gating, UI rendering). The
supervisor's richer per-integration record (broker handle, catalog entry,
crypto material) stays on its side.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegisteredIntegration:
    """Snapshot of one integration as the app sees it.

    ``state`` mirrors the supervisor's runtime view: ``"running"`` for the
    happy path, ``"auth_failed"`` when the broker exited 77 (upstream
    rejected creds; user has to remove + re-add), ``"broken"`` after three
    consecutive failed respawns. Tool gating skips anything not in
    ``"running"`` so the agent doesn't call into a dead broker.

    ``write_allowed`` is the per-integration policy bit. The agent is
    only offered write tools (send, move) when this is true; read-only
    integrations get the read tools and nothing else.
    """

    id: str
    slug: str
    capabilities: frozenset[str]
    state: str = "running"
    write_allowed: bool = False
