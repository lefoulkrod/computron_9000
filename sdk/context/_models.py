"""Data models for context management."""

from pydantic import BaseModel


class ContextStats(BaseModel):
    """Snapshot of estimated context usage at a moment in time.

    Attributes:
        context_used: Estimated tokens currently in conversation history.
        context_limit: The model's configured context window size in tokens.
    """

    context_used: int = 0
    context_limit: int = 0

    @property
    def fill_ratio(self) -> float:
        """Fraction of the context window estimated to be in use (0.0–1.0+)."""
        if self.context_limit <= 0:
            return 0.0
        return self.context_used / self.context_limit
