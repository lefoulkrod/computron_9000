"""Tests for context management strategies."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sdk.context import (
    ContextStats,
    ConversationHistory,
    SummarizeStrategy,
    TriggerPoint,
)
from sdk.providers._models import ChatMessage, ChatResponse, TokenUsage


def _make_fake_chat_response(content: str = "Summary of conversation"):
    """Create a normalized ChatResponse for summarization."""
    return ChatResponse(
        message=ChatMessage(content=content),
        usage=TokenUsage(),
    )


def _make_fake_provider(response):
    """Create a fake provider that returns the given response from chat()."""
    provider = AsyncMock()
    provider.chat.return_value = response
    return provider


@pytest.mark.unit
class TestSummarizeStrategy:
    """Tests for the SummarizeStrategy."""

    def _make_history(self, n_turns: int) -> ConversationHistory:
        """Create a history with a system message and *n* user/assistant turns."""
        messages: list[dict] = [{"role": "system", "content": "sys"}]
        for i in range(n_turns):
            messages.append({"role": "user", "content": f"user-{i}"})
            messages.append({"role": "assistant", "content": f"assistant-{i}"})
        return ConversationHistory(messages)

    def _make_tool_history(self) -> ConversationHistory:
        """Create a history with tool calls to test serialization."""
        return ConversationHistory([
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "find laptops"},
            {"role": "assistant", "content": "I'll search", "tool_calls": [
                {"function": {"name": "browse_page", "arguments": {"url": "amazon.com"}}},
            ]},
            {"role": "tool", "tool_name": "browse_page", "content": "Page snapshot " * 100},
            {"role": "assistant", "content": "Found results", "tool_calls": [
                {"function": {"name": "click", "arguments": {"ref": "5"}}},
            ]},
            {"role": "tool", "tool_name": "click", "content": "Clicked element 5"},
            {"role": "assistant", "content": "The cheapest laptop is $499."},
            {"role": "user", "content": "thanks"},
            {"role": "assistant", "content": "You're welcome!"},
        ])

    def test_trigger_is_before_model_call(self):
        strategy = SummarizeStrategy()
        assert strategy.trigger == TriggerPoint.BEFORE_MODEL_CALL

    def test_should_apply_below_threshold(self):
        strategy = SummarizeStrategy(threshold=0.75)
        stats = ContextStats(context_used=50000, context_limit=128000)
        history = self._make_history(5)
        assert not strategy.should_apply(history, stats)

    def test_should_apply_at_threshold(self):
        strategy = SummarizeStrategy(threshold=0.75)
        stats = ContextStats(context_used=96000, context_limit=128000)
        history = self._make_history(5)
        assert strategy.should_apply(history, stats)

    @pytest.mark.asyncio
    async def test_apply_replaces_old_with_summary(self):
        """Old messages are replaced with a summary, first user msg pinned."""
        strategy = SummarizeStrategy(threshold=0.75, keep_recent=2)
        history = self._make_history(5)  # 1 sys + 10 non-sys
        stats = ContextStats(context_used=100000, context_limit=128000)

        fake_resp = _make_fake_chat_response("This is the summary.")
        fake_provider = _make_fake_provider(fake_resp)

        with patch("sdk.context._strategy.get_provider", return_value=fake_provider):
            with patch("sdk.context._strategy.load_config") as mock_cfg:
                mock_cfg.return_value = _fake_config()
                await strategy.apply(history, stats)

        # system + pinned first user + summary + last 2 non-system messages
        assert len(history) == 5
        assert history.system_message["content"] == "sys"
        # First user message is pinned
        assert history.messages[1]["content"] == "user-0"
        # Summary is inserted after pinned message
        summary_msg = history.messages[2]
        assert summary_msg["role"] == "user"
        assert "summary" in summary_msg["content"].lower()
        assert "This is the summary." in summary_msg["content"]
        # Last 2 messages preserved verbatim
        assert history.messages[3]["content"] == "user-4"
        assert history.messages[4]["content"] == "assistant-4"

    @pytest.mark.asyncio
    async def test_apply_keeps_recent_messages(self):
        """The last keep_recent messages are preserved verbatim."""
        strategy = SummarizeStrategy(threshold=0.75, keep_recent=4)
        history = self._make_history(5)  # 1 sys + 10 non-sys
        stats = ContextStats(context_used=100000, context_limit=128000)

        fake_resp = _make_fake_chat_response("Summary")
        fake_provider = _make_fake_provider(fake_resp)

        with patch("sdk.context._strategy.get_provider", return_value=fake_provider):
            with patch("sdk.context._strategy.load_config") as mock_cfg:
                mock_cfg.return_value = _fake_config()
                await strategy.apply(history, stats)

        # system + pinned first user + summary + 4 recent
        assert len(history) == 7
        non_sys = history.non_system_messages
        assert non_sys[0]["content"] == "user-0"  # pinned
        assert non_sys[1]["role"] == "user"  # summary
        assert "summary" in non_sys[1]["content"].lower()
        # Last 4 are the original messages
        assert non_sys[2]["content"] == "user-3"
        assert non_sys[5]["content"] == "assistant-4"

    @pytest.mark.asyncio
    async def test_apply_preserves_system_message(self):
        strategy = SummarizeStrategy(threshold=0.75, keep_recent=2)
        history = self._make_history(3)  # 1 sys + 6 non-sys
        stats = ContextStats(context_used=100000, context_limit=128000)

        fake_resp = _make_fake_chat_response("Summary")
        fake_provider = _make_fake_provider(fake_resp)

        with patch("sdk.context._strategy.get_provider", return_value=fake_provider):
            with patch("sdk.context._strategy.load_config") as mock_cfg:
                mock_cfg.return_value = _fake_config()
                await strategy.apply(history, stats)

        assert history.system_message is not None
        assert history.system_message["content"] == "sys"
        # First user message is still pinned
        assert history.messages[1]["content"] == "user-0"

    @pytest.mark.asyncio
    async def test_apply_no_op_few_messages(self):
        """Does nothing when there are fewer messages than keep_recent."""
        strategy = SummarizeStrategy(threshold=0.75, keep_recent=4)
        history = self._make_history(1)  # 1 sys + 2 non-sys
        stats = ContextStats(context_used=100000, context_limit=128000)

        await strategy.apply(history, stats)

        assert len(history) == 3  # unchanged

    @pytest.mark.asyncio
    async def test_apply_handles_llm_failure(self):
        """On LLM failure, history is left unchanged."""
        strategy = SummarizeStrategy(threshold=0.75, keep_recent=2)
        history = self._make_history(5)
        original_len = len(history)
        stats = ContextStats(context_used=100000, context_limit=128000)

        fake_provider = AsyncMock()
        fake_provider.chat.side_effect = Exception("LLM unavailable")

        with patch("sdk.context._strategy.get_provider", return_value=fake_provider):
            with patch("sdk.context._strategy.load_config") as mock_cfg:
                mock_cfg.return_value = _fake_config()
                await strategy.apply(history, stats)

        assert len(history) == original_len  # unchanged

    @pytest.mark.asyncio
    async def test_serialization_includes_tool_calls(self):
        """Tool calls and results are included in the serialized conversation."""
        strategy = SummarizeStrategy(threshold=0.75, keep_recent=2)
        history = self._make_tool_history()
        stats = ContextStats(context_used=100000, context_limit=128000)

        fake_resp = _make_fake_chat_response("Summary with tools")
        fake_provider = _make_fake_provider(fake_resp)

        with patch("sdk.context._strategy.get_provider", return_value=fake_provider):
            with patch("sdk.context._strategy.load_config") as mock_cfg:
                mock_cfg.return_value = _fake_config()
                await strategy.apply(history, stats)

        # Verify the provider was called with serialized conversation
        call_args = fake_provider.chat.call_args
        messages = call_args.kwargs["messages"]
        user_msg = messages[1]["content"]
        assert "browse_page" in user_msg
        # "find laptops" is the first user msg — pinned, not in serialized text
        assert history.messages[1]["content"] == "find laptops"

    @pytest.mark.asyncio
    async def test_resolve_model_explicit(self):
        """Explicit summary_model is used when provided."""
        strategy = SummarizeStrategy(summary_model="custom-model:latest")
        history = self._make_history(5)
        stats = ContextStats(context_used=100000, context_limit=128000)

        fake_resp = _make_fake_chat_response("Summary")
        fake_provider = _make_fake_provider(fake_resp)

        with patch("sdk.context._strategy.get_provider", return_value=fake_provider):
            with patch("sdk.context._strategy.load_config") as mock_cfg:
                mock_cfg.return_value = _fake_config()
                await strategy.apply(history, stats)

        call_args = fake_provider.chat.call_args
        assert call_args.kwargs["model"] == "custom-model:latest"


    @pytest.mark.asyncio
    async def test_apply_saves_summary_record(self):
        """A SummaryRecord is saved after successful compaction."""
        strategy = SummarizeStrategy(threshold=0.75, keep_recent=2)
        history = self._make_history(5)
        stats = ContextStats(context_used=100000, context_limit=128000)

        fake_resp = _make_fake_chat_response("This is the summary.")
        fake_provider = _make_fake_provider(fake_resp)

        with patch("sdk.context._strategy.get_provider", return_value=fake_provider):
            with patch("sdk.context._strategy.load_config") as mock_cfg:
                mock_cfg.return_value = _fake_config()
                with patch("sdk.context._strategy.save_summary_record") as mock_save:
                    await strategy.apply(history, stats)

        mock_save.assert_called_once()
        record = mock_save.call_args[0][0]
        assert record.model == "glm-4.7-flash:q8_0"
        assert record.summary_text == "This is the summary."
        # 10 non-sys - 1 pinned - 2 kept = 7 compacted
        assert record.messages_compacted == 7
        assert record.fill_ratio == pytest.approx(100000 / 128000)
        assert record.input_char_count > 0

    @pytest.mark.asyncio
    async def test_apply_no_summary_record_on_failure(self):
        """No SummaryRecord is saved when the LLM call fails."""
        strategy = SummarizeStrategy(threshold=0.75, keep_recent=2)
        history = self._make_history(5)
        stats = ContextStats(context_used=100000, context_limit=128000)

        fake_provider = AsyncMock()
        fake_provider.chat.side_effect = Exception("LLM unavailable")

        with patch("sdk.context._strategy.get_provider", return_value=fake_provider):
            with patch("sdk.context._strategy.load_config") as mock_cfg:
                mock_cfg.return_value = _fake_config()
                with patch("sdk.context._strategy.save_summary_record") as mock_save:
                    await strategy.apply(history, stats)

        mock_save.assert_not_called()


def _fake_config():
    """Create a fake config for tests."""
    cfg = MagicMock()
    cfg.llm.host = "http://localhost:11434"

    # summary config section
    summary = MagicMock()
    summary.model = "glm-4.7-flash:q8_0"
    summary.options = {"temperature": 0.3, "top_k": 20}
    cfg.summary = summary

    return cfg
