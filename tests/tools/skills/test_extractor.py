"""Unit tests for skill extraction utilities."""

from __future__ import annotations

import pytest

from tools.conversations._models import ConversationMetadata, ConversationRecord, TurnRecord, ToolCallRecord
from tools.skills._extractor import (
    _extract_tool_sequence,
    _group_similar_conversations,
    _keyword_similarity,
    _parse_skill_json,
)


def _make_conversation(
    record_id: str,
    user_message: str,
    tools: list[str] | None = None,
) -> ConversationRecord:
    """Build a minimal conversation record for testing."""
    turns = [TurnRecord(role="user", content=user_message)]
    for tool_name in (tools or []):
        turns.append(
            TurnRecord(
                role="tool",
                agent_name="COMPUTRON_9000",
                tool_calls=[ToolCallRecord(name=tool_name, success=True)],
            )
        )
    return ConversationRecord(
        id=record_id,
        user_message=user_message,
        agent="COMPUTRON_9000",
        turns=turns,
        metadata=ConversationMetadata(outcome="success"),
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
class TestGroupSimilarConversations:
    """Tests for conversation clustering."""

    def test_groups_similar(self) -> None:
        """Similar conversations are grouped together."""
        records = [
            _make_conversation("r1", "find pasta recipes"),
            _make_conversation("r2", "find chicken recipes"),
            _make_conversation("r3", "deploy application to server"),
        ]
        groups = _group_similar_conversations(records, threshold=0.3)
        # r1 and r2 share "find" and "recipes"
        assert any(len(g) >= 2 for g in groups)

    def test_no_groups_when_dissimilar(self) -> None:
        """Dissimilar conversations each get their own group."""
        records = [
            _make_conversation("r1", "cats meow purr"),
            _make_conversation("r2", "deploy kubernetes cluster"),
            _make_conversation("r3", "analyze financial data"),
        ]
        groups = _group_similar_conversations(records, threshold=0.5)
        assert all(len(g) == 1 for g in groups)


@pytest.mark.unit
class TestExtractToolSequence:
    """Tests for tool sequence extraction."""

    def test_extracts_tool_calls(self) -> None:
        """Extracts tool names from tool turns."""
        record = _make_conversation("r1", "test", tools=["open_url", "click", "read_page"])
        sequence = _extract_tool_sequence(record)
        assert "open_url" in sequence
        assert "click" in sequence
        assert "read_page" in sequence

    def test_empty_conversation(self) -> None:
        """Conversation with no tool calls returns placeholder."""
        record = ConversationRecord(
            id="r1",
            user_message="hello",
            turns=[TurnRecord(role="user", content="hello")],
        )
        assert _extract_tool_sequence(record) == "(no tool calls)"


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
