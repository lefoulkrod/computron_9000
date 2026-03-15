"""Unit tests for TurnRecorderHook."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from sdk.hooks._turn_recorder import TurnRecorderHook


@pytest.fixture(autouse=True)
def _conv_dir(tmp_path: Path) -> Path:
    """Patch the conversations directory to a temp directory."""
    conv_dir = tmp_path / "conversations"
    with patch(
        "conversations._store._get_conversations_dir",
        return_value=conv_dir,
    ):
        yield conv_dir


def _make_response(content: str = "Hello", tool_calls: list | None = None) -> SimpleNamespace:
    """Build a minimal response object matching ChatResponse shape."""
    message = SimpleNamespace(
        content=content,
        thinking=None,
        tool_calls=tool_calls or [],
    )
    return SimpleNamespace(message=message)


def _make_tool_call(name: str, args: dict | None = None) -> SimpleNamespace:
    """Build a minimal tool call object."""
    return SimpleNamespace(
        function=SimpleNamespace(name=name, arguments=args or {}),
        id=f"call_{name}",
    )


@pytest.mark.unit
class TestTurnRecorderHook:
    """Tests for the turn recording hook."""

    def test_initialization(self) -> None:
        """Verify hook initializes with correct state."""
        hook = TurnRecorderHook(
            user_message="hello",
            agent_name="COMPUTRON_9000",
            model="qwen3:8b",
        )
        assert hook.turn_id
        assert hook._user_message == "hello"

    @pytest.mark.asyncio
    async def test_after_model_records_message(self) -> None:
        """after_model records assistant messages."""
        hook = TurnRecorderHook(
            user_message="test",
            agent_name="COMPUTRON_9000",
            model="qwen3:8b",
        )
        response = _make_response("I'll help you.")
        result = await hook.after_model(response, None, 1, "COMPUTRON_9000")

        assert result is response
        assert len(hook._messages) == 1
        assert hook._messages[0].role == "assistant"
        assert hook._messages[0].content == "I'll help you."

    @pytest.mark.asyncio
    async def test_after_model_with_tool_calls(self) -> None:
        """after_model captures tool calls."""
        hook = TurnRecorderHook(
            user_message="test",
            agent_name="COMPUTRON_9000",
            model="qwen3:8b",
        )
        tc = _make_tool_call("browser_agent_tool", {"instructions": "search"})
        response = _make_response("Searching...", tool_calls=[tc])
        await hook.after_model(response, None, 1, "COMPUTRON_9000")

        assert len(hook._messages) == 1
        assert len(hook._messages[0].tool_calls) == 1
        assert hook._messages[0].tool_calls[0].name == "browser_agent_tool"

    def test_before_tool_returns_none(self) -> None:
        """before_tool should not intercept."""
        hook = TurnRecorderHook(
            user_message="test",
            agent_name="COMPUTRON_9000",
            model="qwen3:8b",
        )
        result = hook.before_tool("click", {"ref": "7"})
        assert result is None
        assert hook._total_tool_calls == 1

    def test_after_tool_records_result(self) -> None:
        """after_tool records tool results and passes through."""
        hook = TurnRecorderHook(
            user_message="test",
            agent_name="COMPUTRON_9000",
            model="qwen3:8b",
        )
        hook.before_tool("click", {"ref": "7"})
        result = hook.after_tool("click", {"ref": "7"}, "Clicked button")

        assert result == "Clicked button"
        assert len(hook._messages) == 1
        assert hook._messages[0].role == "tool"
        assert hook._messages[0].tool_calls[0].duration_ms is not None

    def test_after_tool_stores_full_results(self) -> None:
        """Tool results are stored without truncation."""
        hook = TurnRecorderHook(
            user_message="test",
            agent_name="COMPUTRON_9000",
            model="qwen3:8b",
        )
        long_result = "x" * 1000
        result = hook.after_tool("read_page", {}, long_result)

        # Original result passed through unchanged
        assert len(result) == 1000
        # Stored result is NOT truncated (full fidelity)
        assert len(hook._messages[0].tool_calls[0].result_summary) == 1000

    def test_after_tool_detects_errors(self) -> None:
        """Error results are marked as not successful."""
        hook = TurnRecorderHook(
            user_message="test",
            agent_name="COMPUTRON_9000",
            model="qwen3:8b",
        )
        hook.after_tool("click", {}, "Error: Element not found")
        assert hook._messages[0].tool_calls[0].success is False

    def test_finalize_saves_record(self, _conv_dir: Path) -> None:
        """finalize persists the turn record."""
        hook = TurnRecorderHook(
            user_message="find pasta recipes",
            agent_name="COMPUTRON_9000",
            model="qwen3:8b",
        )
        record = hook.finalize()

        assert record.id == hook.turn_id
        assert record.user_message == "find pasta recipes"
        assert record.agent == "COMPUTRON_9000"
        assert record.metadata.duration_seconds >= 0

        # Check file was written
        turn_file = _conv_dir / f"{record.id}.json"
        assert turn_file.exists()

    @pytest.mark.asyncio
    async def test_agent_chain_tracking(self) -> None:
        """Agent chain tracks all agents that participated."""
        hook = TurnRecorderHook(
            user_message="test",
            agent_name="COMPUTRON_9000",
            model="qwen3:8b",
        )
        response = _make_response("Response")
        await hook.after_model(response, None, 1, "COMPUTRON_9000")
        await hook.after_model(response, None, 2, "BROWSER_AGENT")
        await hook.after_model(response, None, 3, "COMPUTRON_9000")  # Already tracked

        assert hook._agent_chain == ["COMPUTRON_9000", "BROWSER_AGENT"]
