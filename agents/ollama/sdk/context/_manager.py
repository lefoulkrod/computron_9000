"""Context manager orchestrator tying history, tracking, and strategies together."""

import logging
from collections.abc import Callable
from typing import Any

from agents.ollama.sdk.events import AssistantResponse, publish_event
from agents.ollama.sdk.events.models import ContextUsagePayload

from ._history import ConversationHistory
from ._models import ContextStats, TokenUsage
from ._strategy import ContextStrategy, TriggerPoint
from ._token_tracker import OllamaTokenCounter, TokenCounter, TokenTracker

logger = logging.getLogger(__name__)


class ContextManager:
    """Per-agent context manager.

    Receives a reference to a ``ConversationHistory`` (does not own it),
    tracks token usage via a pluggable ``TokenCounter``, and runs
    ``ContextStrategy`` instances at the appropriate trigger points.

    Args:
        history: The conversation history to manage.
        context_limit: Maximum context window size in tokens.
        token_counter: Provider-specific token counter. Defaults to ``OllamaTokenCounter``.
        strategies: Context management strategies to apply.
    """

    def __init__(
        self,
        history: ConversationHistory,
        context_limit: int = 0,
        token_counter: TokenCounter | None = None,
        strategies: list[ContextStrategy] | None = None,
    ) -> None:
        self._history = history
        self._tracker = TokenTracker(
            counter=token_counter or OllamaTokenCounter(),
            context_limit=context_limit,
        )
        self._strategies: list[ContextStrategy] = list(strategies) if strategies else []

    @property
    def stats(self) -> ContextStats:
        """Current context statistics."""
        return self._tracker.stats

    def record_response(self, response: Any) -> TokenUsage:
        """Record token usage from an LLM response and run after-model strategies.

        Publishes a ``ContextUsagePayload`` event so the UI can display
        context window utilisation for this agent.

        Returns:
            The extracted ``TokenUsage`` for this call.
        """
        usage = self._tracker.record(response)
        stats = self._tracker.stats
        logger.debug(
            "Context usage: %d / %d (%.1f%%) — prompt=%d completion=%d",
            stats.context_used, stats.context_limit, stats.fill_ratio * 100,
            usage.prompt_tokens, usage.completion_tokens,
        )
        try:
            publish_event(AssistantResponse(
                event=ContextUsagePayload(
                    type="context_usage",
                    context_used=stats.context_used,
                    context_limit=stats.context_limit,
                    fill_ratio=stats.fill_ratio,
                ),
            ))
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to publish context usage event")
        self._run_strategies(TriggerPoint.AFTER_MODEL_CALL)
        return usage

    def apply_strategies(self) -> None:
        """Run before-model strategies (typically called before an LLM invocation)."""
        self._run_strategies(TriggerPoint.BEFORE_MODEL_CALL)

    def make_after_model_callback(self) -> Callable[[Any], None]:
        """Return a callback suitable for ``tool_loop``'s ``after_model_callbacks``."""
        def _callback(response: Any) -> None:
            self.record_response(response)

        return _callback

    def _run_strategies(self, trigger: TriggerPoint) -> None:
        """Run all strategies matching *trigger*."""
        stats = self._tracker.stats
        for strategy in self._strategies:
            if strategy.trigger != trigger:
                continue
            if strategy.should_apply(self._history, stats):
                logger.info("Applying context strategy: %s", type(strategy).__name__)
                strategy.apply(self._history, stats)
                # Re-read stats after mutation (fill_ratio won't change until
                # next LLM call, but strategies may chain in the future).
                stats = self._tracker.stats
