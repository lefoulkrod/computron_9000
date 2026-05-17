"""Tests for the ContextManager orchestrator."""

from unittest.mock import patch

import pytest

from sdk.context import ContextManager, ConversationHistory, TriggerPoint
from sdk.skills import AgentState


def _empty_state() -> AgentState:
    return AgentState([])


@pytest.mark.unit
def test_initial_stats_with_empty_history():
    cm = ContextManager(
        history=ConversationHistory(),
        agent_state=_empty_state(),
        context_limit=128_000,
    )
    stats = cm.stats
    assert stats.context_used == 0
    assert stats.context_limit == 128_000
    assert stats.fill_ratio == 0.0


@pytest.mark.unit
def test_stats_reflects_history_growth():
    history = ConversationHistory()
    cm = ContextManager(
        history=history,
        agent_state=_empty_state(),
        context_limit=100_000,
    )
    before = cm.stats.context_used
    history.append({"role": "user", "content": "x" * 600})
    after = cm.stats.context_used
    assert after > before


@pytest.mark.unit
def test_stats_includes_tools_from_agent_state():
    def some_tool(name: str) -> str:
        """Echo back.

        Args:
            name: The name to echo.
        """
        return name

    history = ConversationHistory()
    cm_no_tools = ContextManager(
        history=history, agent_state=AgentState([]), context_limit=100_000,
    )
    cm_with_tools = ContextManager(
        history=history, agent_state=AgentState([some_tool]), context_limit=100_000,
    )
    assert cm_with_tools.stats.context_used > cm_no_tools.stats.context_used


@pytest.mark.asyncio
@pytest.mark.unit
async def test_after_model_publishes_event():
    history = ConversationHistory([{"role": "user", "content": "x" * 300}])
    cm = ContextManager(
        history=history,
        agent_state=_empty_state(),
        context_limit=128_000,
    )

    with patch("sdk.context._manager.publish_event") as mock_pub:
        await cm.after_model(iteration=3, max_iterations=10)

    mock_pub.assert_called_once()
    event = mock_pub.call_args[0][0]
    assert event.payload.type == "context_usage"
    assert event.payload.context_used > 0
    assert event.payload.context_limit == 128_000
    assert event.payload.iteration == 3
    assert event.payload.max_iterations == 10


@pytest.mark.asyncio
@pytest.mark.unit
async def test_context_hook_drives_after_model():
    from sdk.hooks import ContextHook

    history = ConversationHistory()
    cm = ContextManager(
        history=history, agent_state=_empty_state(), context_limit=128_000,
    )
    hook = ContextHook(cm)
    sentinel = object()

    with patch("sdk.context._manager.publish_event"):
        result = await hook.after_model(sentinel, history, 1, "test")

    assert result is sentinel


@pytest.mark.asyncio
@pytest.mark.unit
async def test_before_model_strategy_fires_when_threshold_exceeded():
    class _FakeStrategy:
        applied = False

        @property
        def trigger(self) -> TriggerPoint:
            return TriggerPoint.BEFORE_MODEL_CALL

        def should_apply(self, history, stats):
            return stats.fill_ratio >= 0.50

        async def apply(self, history, stats):
            _FakeStrategy.applied = True

    history = ConversationHistory([
        {"role": "system", "content": "system prompt here"},
        {"role": "user", "content": "a fairly long user message to push tokens"},
    ])
    strategy = _FakeStrategy()
    cm = ContextManager(
        history=history,
        agent_state=_empty_state(),
        context_limit=20,
        strategies=[strategy],
    )

    await cm.before_model()
    assert strategy.applied


@pytest.mark.asyncio
@pytest.mark.unit
async def test_before_model_with_no_strategies():
    cm = ContextManager(
        history=ConversationHistory(),
        agent_state=_empty_state(),
        context_limit=128_000,
    )
    await cm.before_model()  # should not raise
