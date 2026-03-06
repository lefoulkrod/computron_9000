"""Tests for context management strategies."""

import pytest

from agents.ollama.sdk.context import (
    ContextStats,
    ConversationHistory,
    DropOldMessagesStrategy,
    TriggerPoint,
)


@pytest.mark.unit
class TestDropOldMessagesStrategy:
    """Tests for the DropOldMessagesStrategy."""

    def _make_history(self, n_user_messages: int) -> ConversationHistory:
        """Create a history with a system message and *n* user/assistant pairs."""
        messages: list[dict] = [{"role": "system", "content": "sys"}]
        for i in range(n_user_messages):
            messages.append({"role": "user", "content": f"user-{i}"})
            messages.append({"role": "assistant", "content": f"assistant-{i}"})
        return ConversationHistory(messages)

    def test_trigger_is_before_model_call(self):
        strategy = DropOldMessagesStrategy()
        assert strategy.trigger == TriggerPoint.BEFORE_MODEL_CALL

    def test_should_apply_below_threshold(self):
        strategy = DropOldMessagesStrategy(threshold=0.85)
        stats = ContextStats(context_used=50000, context_limit=128000)
        history = self._make_history(5)
        assert not strategy.should_apply(history, stats)

    def test_should_apply_at_threshold(self):
        strategy = DropOldMessagesStrategy(threshold=0.85)
        stats = ContextStats(context_used=108800, context_limit=128000)
        history = self._make_history(5)
        assert strategy.should_apply(history, stats)

    def test_apply_drops_oldest_keeps_recent(self):
        strategy = DropOldMessagesStrategy(threshold=0.85, keep_recent=4)
        history = self._make_history(5)  # 1 sys + 10 non-sys = 11 total
        stats = ContextStats(context_used=110000, context_limit=128000)

        strategy.apply(history, stats)

        # Should keep system + 4 most recent non-system messages
        assert len(history) == 5  # 1 sys + 4 non-sys
        assert history.system_message is not None
        assert history.system_message["content"] == "sys"
        # The kept messages should be the last 4 (most recent)
        non_sys = history.non_system_messages
        assert len(non_sys) == 4

    def test_apply_no_op_when_few_messages(self):
        """Does nothing when there are fewer messages than keep_recent."""
        strategy = DropOldMessagesStrategy(threshold=0.85, keep_recent=4)
        history = self._make_history(1)  # 1 sys + 2 non-sys = 3 total
        stats = ContextStats(context_used=110000, context_limit=128000)

        strategy.apply(history, stats)

        assert len(history) == 3  # unchanged

    def test_apply_without_system_message(self):
        """Works correctly when there's no system message."""
        strategy = DropOldMessagesStrategy(threshold=0.85, keep_recent=2)
        history = ConversationHistory([
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
            {"role": "assistant", "content": "d"},
        ])
        stats = ContextStats(context_used=110000, context_limit=128000)

        strategy.apply(history, stats)

        assert len(history) == 2
        assert history.messages[0]["content"] == "c"
        assert history.messages[1]["content"] == "d"
