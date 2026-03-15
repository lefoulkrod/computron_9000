"""Unit tests for skill extraction utilities."""

from __future__ import annotations

import pytest

from conversations._models import MessageRecord, TurnMetadata, TurnRecord, ToolCallRecord
from skills._extractor import (
    _build_conversation_transcript,
    _build_sub_agent_transcript,
    _extract_tool_sequence_from_turns,
    _keyword_similarity,
    _parse_skill_json,
)


def _make_turn(
    turn_id: str,
    user_message: str,
    tools: list[str] | None = None,
) -> TurnRecord:
    """Build a minimal turn record for testing."""
    messages = [MessageRecord(role="user", content=user_message)]
    for tool_name in (tools or []):
        messages.append(
            MessageRecord(
                role="tool",
                agent_name="COMPUTRON_9000",
                tool_calls=[ToolCallRecord(name=tool_name, success=True)],
            )
        )
    return TurnRecord(
        id=turn_id,
        user_message=user_message,
        agent="COMPUTRON_9000",
        messages=messages,
        metadata=TurnMetadata(outcome="success"),
    )


@pytest.mark.unit
class TestKeywordSimilarity:
    """Tests for keyword overlap similarity."""

    def test_identical(self) -> None:
        """Identical strings have similarity 1.0."""
        assert _keyword_similarity("find pasta recipes", "find pasta recipes") == 1.0

    def test_no_overlap(self) -> None:
        """No common words yields 0.0."""
        assert _keyword_similarity("cats dogs", "python javascript") == 0.0

    def test_partial_overlap(self) -> None:
        """Partial overlap yields a value between 0 and 1."""
        sim = _keyword_similarity("find pasta recipes", "find chicken recipes")
        assert 0 < sim < 1

    def test_stopwords_excluded(self) -> None:
        """Common stopwords are excluded."""
        sim = _keyword_similarity("the pasta", "a pasta")
        assert sim == 1.0

    def test_empty_strings(self) -> None:
        """Empty strings return 0.0."""
        assert _keyword_similarity("", "") == 0.0


@pytest.mark.unit
class TestExtractToolSequenceFromTurns:
    """Tests for tool sequence extraction from turns."""

    def test_extracts_tool_calls(self) -> None:
        """Extracts tool names from tool messages."""
        turns = [_make_turn("t1", "test", tools=["open_url", "click", "read_page"])]
        sequence = _extract_tool_sequence_from_turns(turns)
        assert "open_url" in sequence
        assert "click" in sequence
        assert "read_page" in sequence

    def test_empty_turn(self) -> None:
        """Turn with no tool calls returns placeholder."""
        turns = [TurnRecord(
            id="t1",
            user_message="hello",
            messages=[MessageRecord(role="user", content="hello")],
        )]
        assert _extract_tool_sequence_from_turns(turns) == "(no tool calls)"


@pytest.mark.unit
class TestBuildSubAgentTranscript:
    """Tests for sub-agent transcript building."""

    def test_includes_user_messages(self) -> None:
        """User messages (context summaries) are included."""
        messages = [
            {"role": "user", "content": "Navigate to the flights page and search"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "open_url", "arguments": {"url": "https://flights.google.com"}}}
            ]},
        ]
        transcript = _build_sub_agent_transcript(messages)
        assert "Navigate to the flights page" in transcript

    def test_includes_assistant_content(self) -> None:
        """Assistant reasoning text is included."""
        messages = [
            {"role": "assistant", "content": "I need to click the departure field first"},
        ]
        transcript = _build_sub_agent_transcript(messages)
        assert "I need to click the departure field first" in transcript

    def test_includes_thinking(self) -> None:
        """Assistant thinking field is included when present."""
        messages = [
            {"role": "assistant", "content": "", "thinking": "The autocomplete is confusing, let me try a different approach"},
        ]
        transcript = _build_sub_agent_transcript(messages)
        assert "autocomplete is confusing" in transcript

    def test_full_tool_results(self) -> None:
        """Tool results are included without truncation."""
        long_content = "[43] [link] From 462 US dollars round trip " + "x" * 500
        messages = [
            {"role": "tool", "name": "read_page", "content": long_content},
        ]
        transcript = _build_sub_agent_transcript(messages)
        # The full content should be present, not truncated at 200 chars
        assert long_content in transcript

    def test_full_tool_call_args(self) -> None:
        """Tool call arguments are included without truncation."""
        long_url = "https://example.com/" + "a" * 300
        messages = [
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "open_url", "arguments": {"url": long_url}}}
            ]},
        ]
        transcript = _build_sub_agent_transcript(messages)
        assert long_url in transcript

    def test_skips_system_messages(self) -> None:
        """System messages are still skipped."""
        messages = [
            {"role": "system", "content": "You are a browser agent"},
            {"role": "assistant", "content": "Starting task"},
        ]
        transcript = _build_sub_agent_transcript(messages)
        assert "You are a browser agent" not in transcript
        assert "Starting task" in transcript


@pytest.mark.unit
class TestBuildConversationTranscript:
    """Tests for conversation transcript building."""

    def test_basic_transcript(self) -> None:
        """Builds readable transcript from raw messages."""
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Hello there"},
            {"role": "assistant", "content": "Hi! How can I help?"},
        ]
        transcript = _build_conversation_transcript(messages)
        # System messages should be skipped
        assert "System prompt" not in transcript
        assert "[USER] Hello there" in transcript
        assert "[ASSISTANT] Hi! How can I help?" in transcript

    def test_empty_messages(self) -> None:
        """Empty message list returns placeholder."""
        assert _build_conversation_transcript([]) == "(empty conversation)"

    def test_tool_calls_in_transcript(self) -> None:
        """Tool calls in assistant messages are included."""
        messages = [
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "click", "arguments": {"ref": "7"}}}
            ]},
            {"role": "tool", "name": "click", "content": "Clicked button"},
        ]
        transcript = _build_conversation_transcript(messages)
        assert "click" in transcript

    def test_full_user_content(self) -> None:
        """User messages are included without truncation."""
        long_content = "Please search for " + "flights " * 200
        messages = [{"role": "user", "content": long_content}]
        transcript = _build_conversation_transcript(messages)
        assert long_content in transcript

    def test_full_assistant_content(self) -> None:
        """Assistant messages are included without truncation."""
        long_content = "I found the following results: " + "result " * 200
        messages = [{"role": "assistant", "content": long_content}]
        transcript = _build_conversation_transcript(messages)
        assert long_content in transcript

    def test_full_tool_results(self) -> None:
        """Tool results are included without truncation."""
        long_result = "Page content: " + "[7] [button] Search " * 100
        messages = [{"role": "tool", "name": "read_page", "content": long_result}]
        transcript = _build_conversation_transcript(messages)
        assert long_result in transcript

    def test_full_tool_call_args(self) -> None:
        """Tool call argument values are included without truncation."""
        long_value = "a" * 300
        messages = [
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "fill_field", "arguments": {"ref": "5", "value": long_value}}}
            ]},
        ]
        transcript = _build_conversation_transcript(messages)
        assert long_value in transcript

    def test_includes_thinking(self) -> None:
        """Assistant thinking field is included."""
        messages = [
            {"role": "assistant", "content": "ok", "thinking": "Let me reconsider the approach"},
        ]
        transcript = _build_conversation_transcript(messages)
        assert "Let me reconsider the approach" in transcript


@pytest.mark.unit
class TestParseSkillJson:
    """Tests for JSON extraction from LLM output."""

    def test_valid_json(self) -> None:
        """Parses valid JSON."""
        text = '{"name": "test_skill", "description": "A test"}'
        result = _parse_skill_json(text)
        assert result is not None
        assert result["name"] == "test_skill"

    def test_json_with_surrounding_text(self) -> None:
        """Extracts JSON from surrounding text."""
        text = 'Here is the skill:\n{"name": "test"}\nDone.'
        result = _parse_skill_json(text)
        assert result is not None
        assert result["name"] == "test"

    def test_no_response(self) -> None:
        """NO response returns None."""
        assert _parse_skill_json("NO") is None

    def test_invalid_json(self) -> None:
        """Invalid JSON returns None."""
        assert _parse_skill_json("{invalid json}") is None

    def test_no_json(self) -> None:
        """Text without JSON returns None."""
        assert _parse_skill_json("Just some text without braces") is None
