"""Tests for the ContextManager orchestrator."""

from unittest.mock import MagicMock, patch

import pytest

from agents.ollama.sdk.context import (
    ContextManager,
    ContextStats,
    ConversationHistory,
    DropOldMessagesStrategy,
    OllamaTokenCounter,
    TokenUsage,
    TriggerPoint,
)


class _FakeResponse:
    """Mimics Ollama ChatResponse."""

    def __init__(self, prompt_eval_count: int = 0, eval_count: int = 0):
        self.prompt_eval_count = prompt_eval_count
        self.eval_count = eval_count


@pytest.mark.unit
class TestContextManager:
    """Tests for the ContextManager class."""

    def test_initial_stats(self):
        history = ConversationHistory()
        cm = ContextManager(history, context_limit=128000)
        stats = cm.stats
        assert stats.context_used == 0
        assert stats.context_limit == 128000

    def test_record_response(self):
        history = ConversationHistory()
        cm = ContextManager(history, context_limit=128000)
        resp = _FakeResponse(prompt_eval_count=100000, eval_count=5000)

        with patch("agents.ollama.sdk.context._manager.publish_event"):
            usage = cm.record_response(resp)

        assert usage == TokenUsage(prompt_tokens=100000, completion_tokens=5000)
        assert cm.stats.context_used == 105000
        assert cm.stats.fill_ratio == pytest.approx(105000 / 128000)

    def test_record_response_publishes_event(self):
        history = ConversationHistory()
        cm = ContextManager(history, context_limit=128000)
        resp = _FakeResponse(prompt_eval_count=100000, eval_count=5000)

        with patch("agents.ollama.sdk.context._manager.publish_event") as mock_pub:
            cm.record_response(resp)

        mock_pub.assert_called_once()
        event = mock_pub.call_args[0][0]
        assert event.event.type == "context_usage"
        assert event.event.context_used == 105000
        assert event.event.context_limit == 128000

    def test_context_hook_records_response(self):
        from agents.ollama.sdk.hooks import ContextHook

        history = ConversationHistory()
        cm = ContextManager(history, context_limit=128000)
        hook = ContextHook(cm)
        resp = _FakeResponse(prompt_eval_count=50000, eval_count=1000)

        with patch("agents.ollama.sdk.context._manager.publish_event"):
            result = hook.after_model(resp, history, 1, "test")

        assert cm.stats.context_used == 51000
        assert result is resp

    def test_apply_strategies_before_model(self):
        history = ConversationHistory([
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "old1"},
            {"role": "assistant", "content": "old2"},
            {"role": "user", "content": "old3"},
            {"role": "assistant", "content": "old4"},
            {"role": "user", "content": "recent1"},
            {"role": "assistant", "content": "recent2"},
        ])
        strategy = DropOldMessagesStrategy(threshold=0.80, keep_recent=2)
        cm = ContextManager(
            history,
            context_limit=128000,
            strategies=[strategy],
        )

        # Simulate having recorded a response that puts us over threshold
        resp = _FakeResponse(prompt_eval_count=110000, eval_count=5000)
        with patch("agents.ollama.sdk.context._manager.publish_event"):
            cm.record_response(resp)

        # Now apply before-model strategies
        cm.apply_strategies()

        # Strategy should have dropped old messages, keeping 2 recent + system
        assert len(history) == 3
        assert history.system_message is not None

    def test_custom_token_counter(self):
        """Verifies pluggable token counter works."""
        custom_counter = MagicMock()
        custom_counter.extract_usage.return_value = TokenUsage(
            prompt_tokens=42, completion_tokens=8
        )

        history = ConversationHistory()
        cm = ContextManager(history, context_limit=100, token_counter=custom_counter)

        with patch("agents.ollama.sdk.context._manager.publish_event"):
            usage = cm.record_response("fake_response")

        custom_counter.extract_usage.assert_called_once_with("fake_response")
        assert usage.prompt_tokens == 42
        assert cm.stats.context_used == 50

    def test_no_strategies(self):
        """Works fine with no strategies configured."""
        history = ConversationHistory()
        cm = ContextManager(history, context_limit=128000)
        cm.apply_strategies()  # should not raise
