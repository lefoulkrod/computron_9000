"""Tests for _split_into_chunks — ensures tool-call / tool-result pairs
are never separated across chunk boundaries."""

from __future__ import annotations

import pytest

from sdk.context._strategy import _split_into_chunks


# ── helpers ────────────────────────────────────────────────────────────


def _make_msg(role: str, content: str = "", **kwargs) -> dict:
    """Build a minimal message dict."""
    msg: dict = {"role": role, "content": content}
    msg.update(kwargs)
    return msg


def _assistant_with_tool_calls(content: str = "") -> dict:
    return _make_msg(
        "assistant",
        content=content,
        tool_calls=[{"function": {"name": "run_bash_cmd", "arguments": "{}"}}],
    )


def _tool_result(content: str = "result") -> dict:
    return _make_msg("tool", content=content, tool_name="run_bash_cmd")


# ── tests ──────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSplitIntoChunks:
    """Unit tests for _split_into_chunks."""

    # ── tool-call / tool-result pairing ────────────────────────────────

    def test_tool_call_and_result_kept_together(self):
        """A tool call and its result must never be split across chunks."""
        # Build messages where the tool-call + result sit right at a
        # boundary by using a small target_size.
        messages = [
            _make_msg("user", "x" * 80),
            _assistant_with_tool_calls(""),
            _tool_result("y" * 80),
        ]
        # target_size=100: user (80) + assistant (0) = 80, then tool (80)
        # would push to 160 > 100.  Without the fix the tool result would
        # start a new chunk, separating it from the tool call.
        chunks = _split_into_chunks(messages, target_size=100)

        # All three messages must be in the same chunk.
        assert len(chunks) == 1
        assert len(chunks[0]) == 3
        assert chunks[0][0]["role"] == "user"
        assert chunks[0][1]["role"] == "assistant"
        assert chunks[0][2]["role"] == "tool"

    def test_multiple_tool_calls_stay_with_results(self):
        """Multiple tool calls from one assistant message stay with their results."""
        messages = [
            _make_msg("user", "a" * 80),
            _make_msg(
                "assistant",
                content="",
                tool_calls=[
                    {"function": {"name": "f1", "arguments": "{}"}},
                    {"function": {"name": "f2", "arguments": "{}"}},
                ],
            ),
            _make_msg("tool", content="r1", tool_name="f1"),
            _make_msg("tool", content="r2", tool_name="f2"),
        ]
        chunks = _split_into_chunks(messages, target_size=100)

        # All four messages must be in one chunk.
        assert len(chunks) == 1
        assert len(chunks[0]) == 4

    def test_tool_result_not_first_in_new_chunk(self):
        """A tool result should never be the first message in a new chunk."""
        messages = [
            _make_msg("user", "x" * 80),
            _assistant_with_tool_calls(""),
            _tool_result("z" * 80),
            _make_msg("user", "next question"),
        ]
        chunks = _split_into_chunks(messages, target_size=100)

        # The tool result must be in the same chunk as its tool call.
        # Find the chunk containing the tool result.
        tool_chunk = None
        for ch in chunks:
            if any(m.get("role") == "tool" for m in ch):
                tool_chunk = ch
                break

        assert tool_chunk is not None
        # The tool result must NOT be the first message in its chunk.
        first_role = tool_chunk[0]["role"]
        assert first_role != "tool", (
            "tool result should not be the first message in a chunk"
        )

    # ── normal splitting still works ───────────────────────────────────

    def test_normal_messages_split_at_boundary(self):
        """Messages without tool calls still split at size boundaries."""
        messages = [
            _make_msg("user", "a" * 60),
            _make_msg("assistant", "b" * 60),
            _make_msg("user", "c" * 60),
            _make_msg("assistant", "d" * 60),
        ]
        chunks = _split_into_chunks(messages, target_size=100)

        # Should produce multiple chunks.
        assert len(chunks) >= 2
        # Total messages preserved.
        total = sum(len(c) for c in chunks)
        assert total == 4

    def test_single_message_not_split(self):
        """A single message that exceeds target_size still gets its own chunk."""
        messages = [_make_msg("user", "x" * 200)]
        chunks = _split_into_chunks(messages, target_size=100)
        assert len(chunks) == 1
        assert len(chunks[0]) == 1

    def test_empty_messages(self):
        """Empty message list returns no chunks."""
        chunks = _split_into_chunks([], target_size=100)
        assert chunks == []

    # ── edge cases ─────────────────────────────────────────────────────

    def test_tool_call_at_chunk_start_not_split(self):
        """An assistant with tool_calls that would start a new chunk is
        kept with the previous chunk so its tool results stay with it."""
        messages = [
            _make_msg("user", "a" * 80),
            _make_msg("assistant", "b" * 30),  # pushes to 110 > 100
            _assistant_with_tool_calls(""),
            _tool_result("r"),
        ]
        chunks = _split_into_chunks(messages, target_size=100)

        # The assistant-with-tool_calls and its tool result must be
        # together.  They should be in the same chunk.
        for ch in chunks:
            roles = [m["role"] for m in ch]
            if "tool" in roles:
                # The tool call (assistant with tool_calls) must also be here.
                assert any(
                    m.get("role") == "assistant" and m.get("tool_calls")
                    for m in ch
                ), "tool result found without its tool call in the same chunk"

    def test_consecutive_tool_pairs(self):
        """Two consecutive tool-call/result pairs stay intact."""
        messages = [
            _make_msg("user", "x" * 80),
            _assistant_with_tool_calls(""),
            _tool_result("r1" * 40),
            _assistant_with_tool_calls(""),
            _tool_result("r2" * 40),
        ]
        chunks = _split_into_chunks(messages, target_size=100)

        # Each tool result must be in the same chunk as its tool call.
        for ch in chunks:
            tool_results = [m for m in ch if m.get("role") == "tool"]
            tool_calls = [
                m for m in ch
                if m.get("role") == "assistant" and m.get("tool_calls")
            ]
            # If we have tool results, we must have at least as many tool calls.
            if tool_results:
                assert len(tool_calls) >= 1, (
                    "tool results without a tool call in the same chunk"
                )
