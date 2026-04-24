"""Agent-visible tools backed by the integrations subsystem.

Each tool is gated on the set of integration slugs it supports — it's only
included in the agent's tool list when at least one matching integration is
registered. Shared state lives in the ``_state`` submodule.
"""

from tools.integrations._state import (
    has_any_integration,
    mark_added,
    mark_removed,
    refresh_registered_integrations,
    registered_ids,
    registered_integrations,
)

__all__ = [
    "has_any_integration",
    "mark_added",
    "mark_removed",
    "refresh_registered_integrations",
    "registered_ids",
    "registered_integrations",
]
