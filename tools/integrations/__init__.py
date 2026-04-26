"""Agent-visible tools backed by the integrations subsystem.

Each tool is gated on the set of integration slugs it supports — it's only
included in the agent's tool list when at least one matching integration is
registered. Shared state lives in the ``_state`` submodule.
"""

from tools.integrations._state import (
    mark_added,
    mark_removed,
    registered_integrations,
)
from tools.integrations.types import RegisteredIntegration

__all__ = [
    "RegisteredIntegration",
    "mark_added",
    "mark_removed",
    "registered_integrations",
]
