"""Context management for conversation history and compaction."""

from ._estimator import estimate_tokens
from ._history import ConversationHistory
from ._manager import ContextManager
from ._models import ContextStats
from ._strategy import (
    ContextStrategy,
    LLMCompactionStrategy,
    TriggerPoint,
)

# Backwards compat alias
SummarizeStrategy = LLMCompactionStrategy

__all__ = [
    "ContextManager",
    "ContextStats",
    "ContextStrategy",
    "ConversationHistory",
    "LLMCompactionStrategy",
    "SummarizeStrategy",
    "TriggerPoint",
    "estimate_tokens",
]
