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
    """Snapshot of one integration as the app sees it."""

    id: str
    slug: str
    capabilities: frozenset[str]
