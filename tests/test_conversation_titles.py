"""Tests for conversation title generation feature."""

import pytest
from datetime import datetime, UTC
from conversations import ConversationSummary


def test_conversation_summary_with_title():
    """Test that ConversationSummary accepts a title field."""
    summary = ConversationSummary(
        conversation_id="test-conv-123",
        first_message="This is a test message that is quite long",
        title="Test Conversation",
        started_at=datetime.now(UTC).isoformat(),
        turn_count=2,
    )
    assert summary.title == "Test Conversation"
    assert summary.first_message == "This is a test message that is quite long"
    assert summary.conversation_id == "test-conv-123"


def test_conversation_summary_without_title():
    """Test that ConversationSummary works without a title (backward compatibility)."""
    summary = ConversationSummary(
        conversation_id="test-conv-456",
        first_message="Another test message",
        started_at=datetime.now(UTC).isoformat(),
        turn_count=1,
    )
    assert summary.title == ""


def test_conversation_summary_model_dump():
    """Test that ConversationSummary serializes correctly with title."""
    summary = ConversationSummary(
        conversation_id="test-conv-789",
        first_message="Test message content",
        title="My Test Title",
        started_at="2024-01-15T10:30:00+00:00",
        turn_count=5,
    )
    data = summary.model_dump()
    assert data["title"] == "My Test Title"
    assert data["first_message"] == "Test message content"
    assert data["turn_count"] == 5


@pytest.mark.asyncio
async def test_generate_conversation_title():
    """Test the title generation function (requires running Ollama)."""
    from server.message_handler import generate_conversation_title
    
    # Test with a simple message
    title = await generate_conversation_title("What is the capital of France?")
    
    # Should return a non-empty string
    assert isinstance(title, str)
    assert len(title) > 0
    # Should be reasonably short (not the full message)
    assert len(title) < 100
