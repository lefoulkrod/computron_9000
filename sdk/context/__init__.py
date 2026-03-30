"""Context management for conversation history and token tracking."""

from ._history import ConversationHistory
from ._manager import ContextManager
from ._models import ContextStats, TokenUsage
from ._strategy import (
    ContextStrategy,
    LLMCompactionStrategy,
    NudgeCompactionStrategy,
    ToolClearingStrategy,
    TriggerPoint,
)

# Backwards compat alias
SummarizeStrategy = LLMCompactionStrategy
from ._token_tracker import ChatResponseTokenCounter, OllamaTokenCounter, TokenCounter, TokenTracker

__all__ = [
    "ChatResponseTokenCounter",
    "ContextManager",
    "ContextStats",
    "ContextStrategy",
    "ConversationHistory",
    "OllamaTokenCounter",
    "LLMCompactionStrategy",
    "NudgeCompactionStrategy",
    "SummarizeStrategy",
    "ToolClearingStrategy",
    "TokenCounter",
    "TokenTracker",
    "TokenUsage",
    "TriggerPoint",
]
