"""Tests for SummarizeStrategy and related helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sdk.context import ConversationHistory, SummarizeStrategy, ToolClearingStrategy
from sdk.context._models import ContextStats
from sdk.context._strategy import (
    _ARG_CLEAR_CAP,
    _CLEARED_TOOL_RESULT,
    _SUMMARY_PREFIX,
    _extract_prior_summary,
    _find_first_user,
    _serialize_messages,
)


def _make_stats(fill_ratio: float = 0.8) -> ContextStats:
    """Create a ContextStats with the given fill_ratio."""
    return ContextStats(context_used=int(fill_ratio * 1000), context_limit=1000)


def _build_history(messages: list[dict]) -> ConversationHistory:
    return ConversationHistory(messages)


# ---------------------------------------------------------------------------
# Step 1: Summary role is "assistant"
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSummaryRole:
    """Verify that compaction inserts summaries with role=assistant."""

    @pytest.mark.asyncio
    async def test_summary_inserted_as_assistant_role(self):
        """After compaction, the summary message should have role 'assistant'."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "original request"},
            *[{"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"} for i in range(10)],
            # keep_recent_groups=1 keeps the last assistant + anything after
            {"role": "user", "content": "recent user"},
            {"role": "assistant", "content": "recent assistant"},
        ]
        history = _build_history(messages)
        strategy = SummarizeStrategy(threshold=0.5, keep_recent_groups=1, summary_model="test-model")
        stats = _make_stats(0.8)

        with patch.object(strategy, "_summarize", new_callable=AsyncMock) as mock_summarize, \
             patch("sdk.context._strategy.save_summary_record"), \
             patch("sdk.context._strategy.load_config") as mock_cfg:
            mock_summarize.return_value = ("This is the summary.", "test-model")
            mock_cfg.return_value = MagicMock(summary=MagicMock(model="test-model", options={}))

            await strategy.apply(history, stats)

        non_system = history.non_system_messages
        # First message is pinned user, second is the summary
        summary_msg = non_system[1]
        assert summary_msg["role"] == "assistant"
        assert summary_msg["content"].startswith(_SUMMARY_PREFIX)

    @pytest.mark.asyncio
    async def test_tool_pairs_kept_together(self):
        """Tool call + tool result should never be split at the boundary."""
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "old response"},
            {"role": "user", "content": "do something"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "run_bash_cmd", "arguments": "{}"}}
            ]},
            {"role": "tool", "content": "tool result", "tool_name": "run_bash_cmd"},
            {"role": "user", "content": "now fix it"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "run_bash_cmd", "arguments": "{}"}}
            ]},
            {"role": "tool", "content": "fixed", "tool_name": "run_bash_cmd"},
            {"role": "assistant", "content": "Done!"},
        ]
        history = _build_history(messages)
        strategy = SummarizeStrategy(threshold=0.5, keep_recent_groups=2, summary_model="test-model")

        with patch.object(strategy, "_summarize", new_callable=AsyncMock) as mock_summarize, \
             patch("sdk.context._strategy.save_summary_record"), \
             patch("sdk.context._strategy.load_config") as mock_cfg:
            mock_summarize.return_value = ("Summary text.", "test-model")
            mock_cfg.return_value = MagicMock(summary=MagicMock(model="test-model", options={}))

            await strategy.apply(history, _make_stats(0.8))

        non_system = history.non_system_messages
        # Pinned user + summary + kept messages (last 2 assistant groups + interleaved)
        roles = [m["role"] for m in non_system]
        # The last 2 assistant messages are "Done!" and the tool-call before it.
        # The boundary falls right before the tool-call assistant, so the
        # interleaved "now fix it" user message is compacted.
        assert roles == ["user", "assistant", "assistant", "tool", "assistant"]
        # Verify no orphaned tool results — every tool result has a preceding assistant
        for i, m in enumerate(non_system):
            if m.get("role") == "tool":
                assert i > 0
                assert non_system[i - 1].get("role") == "assistant"


# ---------------------------------------------------------------------------
# Serialization: summary skip is role-agnostic
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSerializeMessages:
    """Verify _serialize_messages skips summaries regardless of role."""

    def test_skips_assistant_role_summary(self):
        """Summary with role=assistant (new format) should be skipped."""
        messages = [
            {"role": "assistant", "content": _SUMMARY_PREFIX + "old summary"},
            {"role": "user", "content": "hello"},
        ]
        result = _serialize_messages(messages)
        assert "old summary" not in result
        assert "User: hello" in result

    def test_skips_user_role_summary_legacy(self):
        """Summary with role=user (legacy format) should also be skipped."""
        messages = [
            {"role": "user", "content": _SUMMARY_PREFIX + "old summary"},
            {"role": "assistant", "content": "response"},
        ]
        result = _serialize_messages(messages)
        assert "old summary" not in result
        assert "Assistant: response" in result


# ---------------------------------------------------------------------------
# _extract_prior_summary: role-agnostic
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractPriorSummary:
    """Verify _extract_prior_summary works regardless of message role."""

    def test_finds_assistant_role_summary(self):
        messages = [
            {"role": "assistant", "content": _SUMMARY_PREFIX + "the summary"},
            {"role": "user", "content": "hello"},
        ]
        assert _extract_prior_summary(messages) == "the summary"

    def test_finds_user_role_summary_legacy(self):
        messages = [
            {"role": "user", "content": _SUMMARY_PREFIX + "legacy summary"},
        ]
        assert _extract_prior_summary(messages) == "legacy summary"

    def test_returns_none_when_absent(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        assert _extract_prior_summary(messages) is None


# ---------------------------------------------------------------------------
# _find_first_user: skips assistant summary naturally
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFindFirstUser:
    """Verify _find_first_user finds the real first user message."""

    def test_skips_assistant_summary(self):
        """An assistant-role summary should be invisible to _find_first_user."""
        messages = [
            {"role": "assistant", "content": _SUMMARY_PREFIX + "summary"},
            {"role": "user", "content": "real first"},
        ]
        idx, found = _find_first_user(messages)
        assert found is True
        assert idx == 1

    def test_skips_legacy_user_summary(self):
        """A legacy user-role summary should also be skipped."""
        messages = [
            {"role": "user", "content": _SUMMARY_PREFIX + "summary"},
            {"role": "user", "content": "real first"},
        ]
        idx, found = _find_first_user(messages)
        assert found is True
        assert idx == 1

    def test_finds_first_user_normally(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        idx, found = _find_first_user(messages)
        assert found is True
        assert idx == 0


# ---------------------------------------------------------------------------
# Step 3: SummaryRecord metadata
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSummaryRecordMetadata:
    """Verify SummaryRecord gets conversation_id, agent_name, options."""

    @pytest.mark.asyncio
    async def test_record_includes_metadata(self):
        """After compaction, SummaryRecord should have context metadata."""
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "original"},
            *[{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(8)],
            {"role": "user", "content": "recent"},
            {"role": "assistant", "content": "recent reply"},
        ]
        history = _build_history(messages)
        # Don't set summary_model so _resolve_model falls through to config
        strategy = SummarizeStrategy(threshold=0.5, keep_recent_groups=1)

        saved_records = []

        with patch.object(strategy, "_summarize", new_callable=AsyncMock) as mock_summarize, \
             patch("sdk.context._strategy.save_summary_record", side_effect=saved_records.append), \
             patch("sdk.context._strategy.load_config") as mock_cfg, \
             patch("sdk.context._strategy.load_settings", return_value={"compaction_model": "test-model"}), \
             patch("sdk.context._strategy.get_conversation_id", return_value="conv-123"), \
             patch("sdk.context._strategy.get_current_agent_name", return_value="BROWSER"):
            mock_summarize.return_value = ("Summary.", "test-model")
            mock_cfg.return_value = MagicMock(
                summary=MagicMock(options={"temperature": 0.3}),
            )

            await strategy.apply(history, _make_stats(0.8))

        assert len(saved_records) == 1
        record = saved_records[0]
        assert record.conversation_id == "conv-123"
        assert record.agent_name == "BROWSER"
        assert record.options == {"temperature": 0.3}


# ---------------------------------------------------------------------------
# ToolClearingStrategy: ClearingRecord
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClearingRecord:
    """Verify ToolClearingStrategy saves ClearingRecord with cleared content."""

    @pytest.mark.asyncio
    async def test_saves_clearing_record_on_clear(self):
        """ClearingRecord should contain original content of cleared items."""
        big_result = "x" * 5000
        big_arg_value = "y" * 1000
        messages = [
            {"role": "user", "content": "do something"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "write_file", "arguments": {"path": "/tmp/f", "content": big_arg_value}}}
            ]},
            {"role": "tool", "content": big_result, "tool_name": "write_file"},
            {"role": "assistant", "content": "wrote the file"},
            # Recent — should be protected
            {"role": "user", "content": "now what"},
            {"role": "assistant", "content": "done"},
        ]
        history = _build_history(messages)
        strategy = ToolClearingStrategy(threshold=0.5, keep_recent_groups=1)

        saved_records = []
        with patch("sdk.context._strategy.save_clearing_record", side_effect=saved_records.append), \
             patch("sdk.context._strategy.get_conversation_id", return_value="conv-456"), \
             patch("sdk.context._strategy.get_current_agent_name", return_value="CODER"):
            await strategy.apply(history, _make_stats(0.6))

        assert len(saved_records) == 1
        record = saved_records[0]
        assert record.conversation_id == "conv-456"
        assert record.agent_name == "CODER"
        assert record.results_cleared == 1
        assert record.args_cleared == 1
        assert record.total_chars_freed > 0

        # Verify cleared items contain original content
        result_items = [ci for ci in record.cleared_items if ci.cleared_type == "tool_result"]
        assert len(result_items) == 1
        assert result_items[0].original_content == big_result
        assert result_items[0].tool_name == "write_file"

        arg_items = [ci for ci in record.cleared_items if ci.cleared_type == "tool_arg"]
        assert len(arg_items) == 1
        assert arg_items[0].original_content == big_arg_value
        assert arg_items[0].arg_key == "content"

    @pytest.mark.asyncio
    async def test_no_record_when_nothing_cleared(self):
        """No ClearingRecord should be saved when nothing is cleared."""
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        history = _build_history(messages)
        strategy = ToolClearingStrategy(threshold=0.5, keep_recent_groups=1)

        with patch("sdk.context._strategy.save_clearing_record") as mock_save:
            await strategy.apply(history, _make_stats(0.6))

        mock_save.assert_not_called()
