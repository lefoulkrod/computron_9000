"""In-memory registry mapping integration IDs to their running broker handle.

State is intentionally non-persistent. On supervisor restart we rebuild by
re-reading ``.meta`` files and respawning brokers — fresh process, fresh state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from integrations.supervisor._spawn import BrokerHandle
from integrations.supervisor.types import IntegrationMeta

IntegrationState = Literal["running", "auth_failed", "broken"]


@dataclass
class IntegrationRecord:
    """In-memory state for one active integration.

    Pairs the integration's persisted metadata (slug, label, write_allowed,
    timestamps — the same thing on disk at ``<id>.meta``) with the live
    ``BrokerHandle`` and a snapshot of ``capabilities`` lifted from the
    catalog at construction time. ``capabilities`` is denormalized here
    so the ``list`` verb doesn't need to look the catalog back up.

    Runtime-only fields:

    - ``state`` — ``"running"`` while the broker is up, flipped to
      ``"auth_failed"`` when the broker exits with code 77 (upstream
      rejected creds) and the watcher stops respawning, or ``"broken"``
      when the broker fails to come up three times in a row. The user's
      recovery path for both terminal states is remove + re-add.
    - ``expected_termination`` — set to ``True`` by the supervisor's
      remove flow before SIGTERM so the crash watcher knows this exit
      was on purpose and stays out of the respawn loop.
    """

    meta: IntegrationMeta
    broker: BrokerHandle
    capabilities: frozenset[str]
    state: IntegrationState = "running"
    expected_termination: bool = False


class Registry:
    """Thin typed wrapper around a dict so callers don't reach into internals."""

    def __init__(self) -> None:
        self._by_id: dict[str, IntegrationRecord] = {}

    def add(self, record: IntegrationRecord) -> None:
        self._by_id[record.meta.id] = record

    def get(self, integration_id: str) -> IntegrationRecord | None:
        return self._by_id.get(integration_id)

    def remove(self, integration_id: str) -> IntegrationRecord | None:
        return self._by_id.pop(integration_id, None)

    def list(self) -> list[IntegrationRecord]:
        return list(self._by_id.values())

    def contains(self, integration_id: str) -> bool:
        return integration_id in self._by_id
