"""Tests for empty intent history edge case in LLMCompactionStrategy."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sdk.context import ConversationHistory, SummarizeStrategy
from sdk.context._models import ContextStats
from sdk.context._strategy import _INTENT_PREFIX


def _make_stats(fill_ratio: float = 0.8) -> ContextStats:
    return ContextStats(context_used=int(fill_ratio * 1000), context_limit=1000)


def _build_history(messages: list[dict]) -> ConversationHistory:
    return ConversationHistory(messages)


# ── empty intent history must not replace pinned message ──────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_intent_history_does_not_replace_pinned_message():
    """When _extract_intent returns an empty string, the pinned first user
    message must keep its original content — not be replaced with just the
    intent prefix."""
    original_user_message = "Find me the best flight from Austin to Chicago"

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": original_user_message},
        {"role": "assistant", "content": "Let me search for flights."},
        {"role": "user", "content": "Actually, also check trains."},
        {"role": "assistant", "content": "Checking trains too."},
        {"role": "user", "content": "recent user"},
        {"role": "assistant", "content": "recent assistant"},
    ]
    history = _build_history(messages)
    strategy = SummarizeStrategy(
        threshold=0.5, keep_recent_groups=1, summary_model="test-model",
    )

    with patch.object(strategy, "_summarize", new_callable=AsyncMock) as mock_summarize, \
         patch.object(strategy, "_extract_intent", new_callable=AsyncMock) as mock_extract, \
         patch("sdk.context._strategy.save_summary_record"), \
         patch("sdk.context._strategy.load_config") as mock_cfg:
        mock_summarize.return_value = ("This is the summary.", "test-model")
        # Simulate the summarizer model returning no content
        mock_extract.return_value = ""
        mock_cfg.return_value = MagicMock(summary=MagicMock(model="test-model", options={}))

        await strategy.apply(history, _make_stats(0.8))

    # The pinned first user message (index 1, after system) must still
    # contain the original user message, not just the intent prefix.
    non_system = history.non_system_messages
    pinned_msg = non_system[0]
    assert pinned_msg["role"] == "user"
    assert pinned_msg["content"] == original_user_message, (
        f"Expected original message '{original_user_message}', "
        f"got '{pinned_msg['content']}'"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_none_intent_history_does_not_replace_pinned_message():
    """When _extract_intent returns None (exception path), the pinned message
    must also be preserved."""
    original_user_message = "Find me the best flight from Austin to Chicago"

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": original_user_message},
        {"role": "assistant", "content": "Let me search for flights."},
        {"role": "user", "content": "Actually, also check trains."},
        {"role": "assistant", "content": "Checking trains too."},
        {"role": "user", "content": "recent user"},
        {"role": "assistant", "content": "recent assistant"},
    ]
    history = _build_history(messages)
    strategy = SummarizeStrategy(
        threshold=0.5, keep_recent_groups=1, summary_model="test-model",
    )

    with patch.object(strategy, "_summarize", new_callable=AsyncMock) as mock_summarize, \
         patch.object(strategy, "_extract_intent", new_callable=AsyncMock) as mock_extract, \
         patch("sdk.context._strategy.save_summary_record"), \
         patch("sdk.context._strategy.load_config") as mock_cfg:
        mock_summarize.return_value = ("This is the summary.", "test-model")
        # Simulate the summarizer model returning None (e.g. exception caught)
        mock_extract.return_value = None
        mock_cfg.return_value = MagicMock(summary=MagicMock(model="test-model", options={}))

        await strategy.apply(history, _make_stats(0.8))

    non_system = history.non_system_messages
    pinned_msg = non_system[0]
    assert pinned_msg["role"] == "user"
    assert pinned_msg["content"] == original_user_message, (
        f"Expected original message '{original_user_message}', "
        f"got '{pinned_msg['content']}'"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_valid_intent_history_still_replaces_pinned_message():
    """When _extract_intent returns a non-empty string, the pinned message
    should still be replaced (the normal, working case)."""
    original_user_message = "Find me the best flight from Austin to Chicago"
    extracted_intent = "User originally wanted flights AUS→ORD, then added trains."

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": original_user_message},
        {"role": "assistant", "content": "Let me search for flights."},
        {"role": "user", "content": "Actually, also check trains."},
        {"role": "assistant", "content": "Checking trains too."},
        {"role": "user", "content": "recent user"},
        {"role": "assistant", "content": "recent assistant"},
    ]
    history = _build_history(messages)
    strategy = SummarizeStrategy(
        threshold=0.5, keep_recent_groups=1, summary_model="test-model",
    )

    with patch.object(strategy, "_summarize", new_callable=AsyncMock) as mock_summarize, \
         patch.object(strategy, "_extract_intent", new_callable=AsyncMock) as mock_extract, \
         patch("sdk.context._strategy.save_summary_record"), \
         patch("sdk.context._strategy.load_config") as mock_cfg:
        mock_summarize.return_value = ("This is the summary.", "test-model")
        mock_extract.return_value = extracted_intent
        mock_cfg.return_value = MagicMock(summary=MagicMock(model="test-model", options={}))

        await strategy.apply(history, _make_stats(0.8))

    non_system = history.non_system_messages
    pinned_msg = non_system[0]
    assert pinned_msg["role"] == "user"
    assert pinned_msg["content"] == _INTENT_PREFIX + extracted_intent, (
        f"Expected intent prefix + '{extracted_intent}', "
        f"got '{pinned_msg['content']}'"
    )
