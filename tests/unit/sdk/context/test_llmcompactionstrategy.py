"""Tests for SummarizeStrategy and related helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sdk.context import ConversationHistory, SummarizeStrategy
from sdk.context._models import ContextStats
from sdk.context._strategy import (
    _SUMMARY_PREFIX,
    _extract_prior_summary,
    _find_first_user,
    _serialize_messages,
)


def _make_stats(fill_ratio: float = 0.8) -> ContextStats:
    return ContextStats(context_used=int(fill_ratio * 1000), context_limit=1000)


def _build_history(messages: list[dict]) -> ConversationHistory:
    return ConversationHistory(messages)


# ── compaction inserts summaries with role=assistant ────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_summary_inserted_as_assistant_role():
    """After compaction, the summary message should have role 'assistant'."""
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "original request"},
        *[{"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"} for i in range(10)],
        {"role": "user", "content": "recent user"},
        {"role": "assistant", "content": "recent assistant"},
    ]
    history = _build_history(messages)
    strategy = SummarizeStrategy(threshold=0.5, keep_recent_groups=1, summary_model="test-model")

    with patch.object(strategy, "_summarize", new_callable=AsyncMock) as mock_summarize, \
         patch("sdk.context._strategy.save_summary_record"), \
         patch("sdk.context._strategy.load_config") as mock_cfg:
        mock_summarize.return_value = ("This is the summary.", "test-model")
        mock_cfg.return_value = MagicMock(summary=MagicMock(model="test-model", options={}))

        await strategy.apply(history, _make_stats(0.8))

    non_system = history.non_system_messages
    summary_msg = non_system[1]
    assert summary_msg["role"] == "assistant"
    assert summary_msg["content"].startswith(_SUMMARY_PREFIX)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_pairs_kept_together():
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
    roles = [m["role"] for m in non_system]
    assert roles == ["user", "assistant", "assistant", "tool", "assistant"]
    for i, m in enumerate(non_system):
        if m.get("role") == "tool":
            assert i > 0
            assert non_system[i - 1].get("role") == "assistant"


# ── _serialize_messages: summary skip is role-agnostic ─────────────────


@pytest.mark.unit
def test_serialize_skips_assistant_role_summary():
    """Summary with role=assistant (new format) should be skipped."""
    messages = [
        {"role": "assistant", "content": _SUMMARY_PREFIX + "old summary"},
        {"role": "user", "content": "hello"},
    ]
    result = _serialize_messages(messages)
    assert "old summary" not in result
    assert "User: hello" in result


@pytest.mark.unit
def test_serialize_skips_user_role_summary_legacy():
    """Summary with role=user (legacy format) should also be skipped."""
    messages = [
        {"role": "user", "content": _SUMMARY_PREFIX + "old summary"},
        {"role": "assistant", "content": "response"},
    ]
    result = _serialize_messages(messages)
    assert "old summary" not in result
    assert "Assistant: response" in result


# ── _extract_prior_summary ─────────────────────────────────────────────


@pytest.mark.unit
def test_extract_prior_summary_finds_assistant_role():
    messages = [
        {"role": "assistant", "content": _SUMMARY_PREFIX + "the summary"},
        {"role": "user", "content": "hello"},
    ]
    assert _extract_prior_summary(messages) == "the summary"


@pytest.mark.unit
def test_extract_prior_summary_finds_legacy_user_role():
    messages = [
        {"role": "user", "content": _SUMMARY_PREFIX + "legacy summary"},
    ]
    assert _extract_prior_summary(messages) == "legacy summary"


@pytest.mark.unit
def test_extract_prior_summary_returns_none_when_absent():
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    assert _extract_prior_summary(messages) is None


# ── _find_first_user ───────────────────────────────────────────────────


@pytest.mark.unit
def test_find_first_user_skips_assistant_summary():
    """An assistant-role summary should be invisible to _find_first_user."""
    messages = [
        {"role": "assistant", "content": _SUMMARY_PREFIX + "summary"},
        {"role": "user", "content": "real first"},
    ]
    idx, found = _find_first_user(messages)
    assert found is True
    assert idx == 1


@pytest.mark.unit
def test_find_first_user_skips_legacy_user_summary():
    """A legacy user-role summary should also be skipped."""
    messages = [
        {"role": "user", "content": _SUMMARY_PREFIX + "summary"},
        {"role": "user", "content": "real first"},
    ]
    idx, found = _find_first_user(messages)
    assert found is True
    assert idx == 1


@pytest.mark.unit
def test_find_first_user_finds_normal_first():
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    idx, found = _find_first_user(messages)
    assert found is True
    assert idx == 0


# ── SummaryRecord metadata ─────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_summary_record_includes_metadata():
    """After compaction, SummaryRecord should have context metadata."""
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "original"},
        *[{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(8)],
        {"role": "user", "content": "recent"},
        {"role": "assistant", "content": "recent reply"},
    ]
    history = _build_history(messages)
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
