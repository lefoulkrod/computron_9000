"""Context manager orchestrator tying history and strategies together."""

import logging

from rich.console import Console
from rich.text import Text

from sdk.events import AgentEvent, ContextUsagePayload, publish_event
from sdk.skills import AgentState

from ._estimator import estimate_tokens
from ._history import ConversationHistory
from ._models import ContextStats
from ._strategy import ContextStrategy, TriggerPoint

logger = logging.getLogger(__name__)
_console = Console(stderr=True)


class ContextManager:
    """Per-agent context manager.

    Holds references to the live ``ConversationHistory`` and ``AgentState``
    (does not own either), computes the current token estimate over both
    on demand, and runs ``ContextStrategy`` instances at the appropriate
    trigger points.

    Args:
        history: The conversation history to manage.
        agent_state: The live agent state — its ``.tools`` property is
            read at every stats lookup so dynamically loaded skills are
            included in the estimate.
        context_limit: Maximum context window size in tokens.
        strategies: Context management strategies to apply.
        agent_name: Optional label used in log output.
    """

    def __init__(
        self,
        history: ConversationHistory,
        agent_state: AgentState,
        context_limit: int,
        strategies: list[ContextStrategy] | None = None,
        agent_name: str = "",
    ) -> None:
        self._history = history
        self._agent_state = agent_state
        self._context_limit = context_limit
        self._agent_name = agent_name
        self._strategies: list[ContextStrategy] = list(strategies) if strategies else []

    @property
    def stats(self) -> ContextStats:
        """Current context statistics estimated from history + current tools."""
        used = estimate_tokens(self._history.messages, tools=self._agent_state.tools)
        return ContextStats(context_used=used, context_limit=self._context_limit)

    async def after_model(
        self, *,
        iteration: int | None = None,
        max_iterations: int | None = None,
    ) -> None:
        """Publish a context usage event and run after-model strategies."""
        stats = self.stats
        if logger.isEnabledFor(logging.DEBUG):
            _log_context_bar(stats, self._agent_name)
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

    async def before_model(self) -> None:
        """Run before-model strategies."""
        await self._run_strategies(TriggerPoint.BEFORE_MODEL_CALL)

    async def _run_strategies(self, trigger: TriggerPoint) -> None:
        """Run all strategies matching *trigger*."""
        stats = self.stats
        for strategy in self._strategies:
            if strategy.trigger != trigger:
                continue
            if strategy.should_apply(self._history, stats):
                logger.info("Applying context strategy: %s", type(strategy).__name__)
                await strategy.apply(self._history, stats)
                # Re-read stats so chained strategies see the updated estimate.
                stats = self.stats


def _log_context_bar(stats: ContextStats, agent_name: str = "") -> None:
    """Render a visual context-usage bar to the console."""
    pct = stats.fill_ratio * 100
    if pct < 50:
        bar_style = "green"
    elif pct < 80:
        bar_style = "yellow"
    else:
        bar_style = "red"

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

    _console.print(line)
