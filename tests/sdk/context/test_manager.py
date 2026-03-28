"""Tests for the ContextManager orchestrator."""

from unittest.mock import MagicMock, patch

import pytest

from sdk.context import (
    ContextManager,
    ConversationHistory,
    TokenUsage,
    TriggerPoint,
)


class _FakeUsage:
    """Mimics normalized TokenUsage on a ChatResponse."""

    def __init__(self, prompt_tokens: int = 0, completion_tokens: int = 0):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _FakeResponse:
    """Mimics a normalized ChatResponse with a usage attribute."""

    def __init__(self, prompt_eval_count: int = 0, eval_count: int = 0):
        self.usage = _FakeUsage(
            prompt_tokens=prompt_eval_count,
            completion_tokens=eval_count,
        )


@pytest.mark.unit
class TestContextManager:
    """Tests for the ContextManager class."""

    def test_initial_stats(self):
        history = ConversationHistory()
        cm = ContextManager(history, context_limit=128000)
        stats = cm.stats
        assert stats.context_used == 0
        assert stats.context_limit == 128000

    @pytest.mark.asyncio
    async def test_record_response(self):
        history = ConversationHistory()
        cm = ContextManager(history, context_limit=128000)
        resp = _FakeResponse(prompt_eval_count=100000, eval_count=5000)

        with patch("sdk.context._manager.publish_event"):
            usage = await cm.record_response(resp)

        assert usage == TokenUsage(prompt_tokens=100000, completion_tokens=5000)
        assert cm.stats.context_used == 105000
        assert cm.stats.fill_ratio == pytest.approx(105000 / 128000)

    @pytest.mark.asyncio
    async def test_record_response_publishes_event(self):
        history = ConversationHistory()
        cm = ContextManager(history, context_limit=128000)
        resp = _FakeResponse(prompt_eval_count=100000, eval_count=5000)

        with patch("sdk.context._manager.publish_event") as mock_pub:
            await cm.record_response(resp)

        mock_pub.assert_called_once()
        event = mock_pub.call_args[0][0]
        assert event.payload.type == "context_usage"
        assert event.payload.context_used == 105000
        assert event.payload.context_limit == 128000

    @pytest.mark.asyncio
    async def test_context_hook_records_response(self):
        from sdk.hooks import ContextHook

        history = ConversationHistory()
        cm = ContextManager(history, context_limit=128000)
        hook = ContextHook(cm)
        resp = _FakeResponse(prompt_eval_count=50000, eval_count=1000)

        with patch("sdk.context._manager.publish_event"):
            result = await hook.after_model(resp, history, 1, "test")

        assert cm.stats.context_used == 51000
        assert result is resp

    @pytest.mark.asyncio
    async def test_apply_strategies_before_model(self):
        """Verifies that a strategy fires when fill_ratio exceeds its threshold."""

        class _FakeStrategy:
            applied = False

            @property
            def trigger(self) -> TriggerPoint:
                return TriggerPoint.BEFORE_MODEL_CALL

            def should_apply(self, history, stats):
                return stats.fill_ratio >= 0.80

            async def apply(self, history, stats):
                _FakeStrategy.applied = True

        history = ConversationHistory([
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "old1"},
        ])
        strategy = _FakeStrategy()
        cm = ContextManager(
            history,
            context_limit=128000,
            strategies=[strategy],
        )

        # Simulate having recorded a response that puts us over threshold
        resp = _FakeResponse(prompt_eval_count=110000, eval_count=5000)
        with patch("sdk.context._manager.publish_event"):
            await cm.record_response(resp)

        await cm.apply_strategies()
        assert strategy.applied

    @pytest.mark.asyncio
    async def test_custom_token_counter(self):
        """Verifies pluggable token counter works."""
        custom_counter = MagicMock()
        custom_counter.extract_usage.return_value = TokenUsage(
            prompt_tokens=42, completion_tokens=8
        )

        history = ConversationHistory()
        cm = ContextManager(history, context_limit=100, token_counter=custom_counter)

        with patch("sdk.context._manager.publish_event"):
            usage = await cm.record_response("fake_response")

        custom_counter.extract_usage.assert_called_once_with("fake_response")
        assert usage.prompt_tokens == 42
        assert cm.stats.context_used == 50

    @pytest.mark.asyncio
    async def test_no_strategies(self):
        """Works fine with no strategies configured."""
        history = ConversationHistory()
        cm = ContextManager(history, context_limit=128000)
        await cm.apply_strategies()  # should not raise
