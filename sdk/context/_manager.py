"""Context manager orchestrator tying history, tracking, and strategies together."""

import logging
from typing import Any

from rich.console import Console
from rich.text import Text

from sdk.events import AgentEvent, ContextUsagePayload, publish_event

from ._history import ConversationHistory
from ._models import ContextStats, TokenUsage
from ._strategy import ContextStrategy, TriggerPoint
from ._token_tracker import ChatResponseTokenCounter, OllamaTokenCounter, TokenCounter, TokenTracker

logger = logging.getLogger(__name__)
_console = Console(stderr=True)


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
        agent_name: str = "",
    ) -> None:
        self._history = history
        self._agent_name = agent_name
        self._tracker = TokenTracker(
            counter=token_counter or ChatResponseTokenCounter(),
            context_limit=context_limit,
        )
        self._strategies: list[ContextStrategy] = list(strategies) if strategies else []

    @property
    def stats(self) -> ContextStats:
        """Current context statistics."""
        return self._tracker.stats

    async def record_response(
        self, response: Any, *,
        iteration: int | None = None,
        max_iterations: int | None = None,
    ) -> TokenUsage:
        """Record token usage from an LLM response and run after-model strategies.

        Publishes a ``ContextUsagePayload`` event so the UI can display
        context window utilisation for this agent.

        Returns:
            The extracted ``TokenUsage`` for this call.
        """
        usage = self._tracker.record(response)
        stats = self._tracker.stats
        if logger.isEnabledFor(logging.DEBUG):
            _log_context_bar(stats, usage, self._agent_name)
        try:
            publish_event(AgentEvent(payload=ContextUsagePayload(
                type="context_usage",
                context_used=stats.context_used,
                context_limit=stats.context_limit,
                fill_ratio=stats.fill_ratio,
                iteration=iteration,
                max_iterations=max_iterations,
            )))
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to publish context usage event")
        await self._run_strategies(TriggerPoint.AFTER_MODEL_CALL)
        return usage

    async def apply_strategies(self) -> None:
        """Run before-model strategies (typically called before an LLM invocation)."""
        await self._run_strategies(TriggerPoint.BEFORE_MODEL_CALL)

    async def _run_strategies(self, trigger: TriggerPoint) -> None:
        """Run all strategies matching *trigger*."""
        stats = self._tracker.stats
        for strategy in self._strategies:
            if strategy.trigger != trigger:
                continue
            if strategy.should_apply(self._history, stats):
                logger.info("Applying context strategy: %s", type(strategy).__name__)
                await strategy.apply(self._history, stats)
                # Re-read stats after mutation (fill_ratio won't change until
                # next LLM call, but strategies may chain in the future).
                stats = self._tracker.stats


def _log_context_bar(stats: ContextStats, usage: TokenUsage, agent_name: str = "") -> None:
    """Render a visual context-usage bar to the console."""
    pct = stats.fill_ratio * 100
    # Color the bar based on fill level
    if pct < 50:
        bar_style = "green"
    elif pct < 80:
        bar_style = "yellow"
    else:
        bar_style = "red"

    # Build a visual bar using block characters
    bar_width = 30
    filled = int(bar_width * min(stats.fill_ratio, 1.0))
    empty = bar_width - filled
    bar_text = Text()
    bar_text.append("━" * filled, style=bar_style)
    bar_text.append("━" * empty, style="grey23")

    line = Text()
    if agent_name:
        line.append(f"  {agent_name}", style="bold cyan")
        line.append("  ", style="default")
    line.append("Context  ", style="bold")
    line.append_text(bar_text)
    line.append(f"  {stats.context_used:,}", style="bold")
    line.append(f" / {stats.context_limit:,}", style="dim")
    line.append(f"  ({pct:.1f}%)", style=bar_style)
    line.append(f"   prompt={usage.prompt_tokens:,}  completion={usage.completion_tokens:,}", style="dim")

    _console.print(line)
