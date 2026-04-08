"""Data models for context management."""

from __future__ import annotations

from pydantic import BaseModel


class TokenUsage(BaseModel):
    """Token counts from a single LLM call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0


class ContextStats(BaseModel):
    """Minimal stats for context management decisions.

    Attributes:
        context_used: Prompt + completion tokens from the last LLM call.
        context_limit: The model's context window size (num_ctx).
    """

    context_used: int = 0
    context_limit: int = 0

    @property
    def fill_ratio(self) -> float:
        """Fraction of the context window consumed on the last call (0.0–1.0+)."""
        if self.context_limit <= 0:
            return 0.0
        return self.context_used / self.context_limit
