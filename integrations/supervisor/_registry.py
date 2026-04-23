"""In-memory registry mapping integration IDs to their running broker handle.

State is intentionally non-persistent. On supervisor restart we rebuild by
re-reading ``.meta`` files and respawning brokers — fresh process, fresh state.
"""

from __future__ import annotations

from dataclasses import dataclass

from integrations.supervisor._spawn import BrokerHandle
from integrations.supervisor.types import IntegrationMeta


@dataclass
class IntegrationRecord:
    """In-memory state for one active integration.

    Pairs the integration's metadata (slug, label, write_allowed, timestamps —
    the same thing on disk at ``<id>.meta``) with the live ``BrokerHandle``
    for its running broker subprocess. The record exists from ``add`` to
    ``remove`` and is rebuilt on supervisor restart by respawning the broker
    from persisted metadata.
    """

    meta: IntegrationMeta
    broker: BrokerHandle


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
