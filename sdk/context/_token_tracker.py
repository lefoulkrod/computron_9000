"""Pluggable token counting and cumulative tracking."""

from typing import Any, Protocol

from ._models import ContextStats, TokenUsage


class TokenCounter(Protocol):
    """Provider-agnostic interface for extracting token counts from LLM responses."""

    def extract_usage(self, response: Any) -> TokenUsage:
        """Extract token usage from a provider's response object."""
        ...


class OllamaTokenCounter:
    """Extracts token counts from Ollama ``ChatResponse`` objects.

    .. deprecated::
        Use ``ChatResponseTokenCounter`` instead, which works with the
        normalized ``ChatResponse`` from any provider.
    """

    def extract_usage(self, response: Any) -> TokenUsage:
        """Read ``prompt_eval_count`` and ``eval_count`` from the response."""
        return TokenUsage(
            prompt_tokens=getattr(response, "prompt_eval_count", 0) or 0,
            completion_tokens=getattr(response, "eval_count", 0) or 0,
        )


class ChatResponseTokenCounter:
    """Extracts token counts from normalized ``ChatResponse.usage``."""

    def extract_usage(self, response: Any) -> TokenUsage:
        """Read token counts from the provider-agnostic ``usage`` field."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return TokenUsage()
        return TokenUsage(
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )


class TokenTracker:
    """Accumulates token usage across multiple LLM calls.

    Args:
        counter: Provider-specific token counter implementation.
        context_limit: Maximum context window size in tokens.
    """

    def __init__(self, counter: TokenCounter, context_limit: int = 0) -> None:
        self._counter = counter
        self._context_limit = context_limit
        self._last_usage: TokenUsage | None = None

    def record(self, response: Any) -> TokenUsage:
        """Extract and store token usage from an LLM response.

        Returns:
            The extracted ``TokenUsage`` for this call.
        """
        usage = self._counter.extract_usage(response)
        self._last_usage = usage
        return usage

    @property
    def stats(self) -> ContextStats:
        """Current context statistics based on the most recent LLM call."""
        if self._last_usage is None:
            return ContextStats(context_limit=self._context_limit)
        return ContextStats(
            context_used=self._last_usage.prompt_tokens + self._last_usage.completion_tokens,
            context_limit=self._context_limit,
        )

    @property
    def last_usage(self) -> TokenUsage | None:
        """Token usage from the most recent call, or *None* if no calls recorded."""
        return self._last_usage
