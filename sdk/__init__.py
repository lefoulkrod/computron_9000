"""Public exports for the agent SDK helpers used by the project.

This module re-exports commonly used helpers for convenience.
"""

from .context import ContextManager, ConversationHistory
from .hooks import (
    BudgetGuard,
    ContextHook,
    LoggingHook,
    LoopDetector,
    PersistenceHook,
    StopHook,
    default_hooks,
)
from .turn import run_turn
from .providers import LLMRuntimeStats, llm_runtime_stats

# Imported last so that sdk.context, sdk.hooks, sdk.turn (without _executor)
# and sdk.providers are all fully loaded before the executor module — which
# pulls from all of them — is initialized. ``Conversation`` lives in its
# own minimal module so importers below the SDK layer can grab it without
# pulling in the full executor.
from .turn._conversation import Conversation
from .turn._executor import TurnExecutor
from .turn._persistence import TurnPersistence

__all__ = [
    "BudgetGuard",
    "ContextHook",
    "ContextManager",
    "Conversation",
    "ConversationHistory",
    "LLMRuntimeStats",
    "LoggingHook",
    "LoopDetector",
    "PersistenceHook",
    "StopHook",
    "TurnExecutor",
    "TurnPersistence",
    "default_hooks",
    "llm_runtime_stats",
    "run_turn",
]
