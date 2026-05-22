"""Tests for _split_into_chunks — ensures tool-call / tool-result pairs
are never separated across chunk boundaries."""

from __future__ import annotations

import pytest

from sdk.context._strategy import _split_into_chunks


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


@pytest.mark.unit
def test_tool_call_and_result_kept_together():
    """A tool call and its result must never be split across chunks."""
    # Sized so the tool result would start a new chunk without the fix.
    messages = [
        _make_msg("user", "x" * 80),
        _assistant_with_tool_calls(""),
        _tool_result("y" * 80),
    ]
    chunks = _split_into_chunks(messages, target_size=100)

    assert len(chunks) == 1
    assert len(chunks[0]) == 3
    assert chunks[0][0]["role"] == "user"
    assert chunks[0][1]["role"] == "assistant"
    assert chunks[0][2]["role"] == "tool"


@pytest.mark.unit
def test_multiple_tool_calls_stay_with_results():
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

    assert len(chunks) == 1
    assert len(chunks[0]) == 4


@pytest.mark.unit
def test_tool_result_not_first_in_new_chunk():
    """A tool result should never be the first message in a new chunk."""
    messages = [
        _make_msg("user", "x" * 80),
        _assistant_with_tool_calls(""),
        _tool_result("z" * 80),
        _make_msg("user", "next question"),
    ]
    chunks = _split_into_chunks(messages, target_size=100)

    tool_chunk = None
    for ch in chunks:
        if any(m.get("role") == "tool" for m in ch):
            tool_chunk = ch
            break

    assert tool_chunk is not None
    first_role = tool_chunk[0]["role"]
    assert first_role != "tool", (
        "tool result should not be the first message in a chunk"
    )


@pytest.mark.unit
def test_normal_messages_split_at_boundary():
    """Messages without tool calls still split at size boundaries."""
    messages = [
        _make_msg("user", "a" * 60),
        _make_msg("assistant", "b" * 60),
        _make_msg("user", "c" * 60),
        _make_msg("assistant", "d" * 60),
    ]
    chunks = _split_into_chunks(messages, target_size=100)

    assert len(chunks) >= 2
    total = sum(len(c) for c in chunks)
    assert total == 4


@pytest.mark.unit
def test_single_message_not_split():
    """A single message that exceeds target_size still gets its own chunk."""
    messages = [_make_msg("user", "x" * 200)]
    chunks = _split_into_chunks(messages, target_size=100)
    assert len(chunks) == 1
    assert len(chunks[0]) == 1


@pytest.mark.unit
def test_empty_messages():
    """Empty message list returns no chunks."""
    chunks = _split_into_chunks([], target_size=100)
    assert chunks == []


@pytest.mark.unit
def test_consecutive_tool_pairs():
    """Two consecutive tool-call/result pairs stay intact."""
    messages = [
        _make_msg("user", "x" * 80),
        _assistant_with_tool_calls(""),
        _tool_result("r1" * 40),
        _assistant_with_tool_calls(""),
        _tool_result("r2" * 40),
    ]
    chunks = _split_into_chunks(messages, target_size=100)

    for ch in chunks:
        tool_results = [m for m in ch if m.get("role") == "tool"]
        tool_calls = [
            m for m in ch
            if m.get("role") == "assistant" and m.get("tool_calls")
        ]
        if tool_results:
            assert len(tool_calls) >= 1, (
                "tool results without a tool call in the same chunk"
            )


@pytest.mark.unit
def test_empty_tool_calls_list_splits_normally():
    """An assistant with an empty tool_calls list is treated like a
    regular assistant message — normal splitting applies."""
    messages = [
        _make_msg("user", "a" * 80),
        _make_msg("assistant", content="b" * 80, tool_calls=[]),
        _make_msg("user", "c" * 80),
    ]
    chunks = _split_into_chunks(messages, target_size=100)

    # Without a real tool call to protect, splits should happen at size boundaries.
    assert len(chunks) >= 2
    total = sum(len(c) for c in chunks)
    assert total == 3


@pytest.mark.unit
def test_second_tool_result_not_split_from_assistant():
    """When an assistant issues two tool calls, both results stay in the
    same chunk as the assistant — the second tool result must not be
    pushed to a new chunk."""
    messages = [
        _make_msg("user", "x" * 80),
        _make_msg(
            "assistant",
            content="",
            tool_calls=[
                {"function": {"name": "read_file", "arguments": "{}"}},
                {"function": {"name": "grep", "arguments": "{}"}},
            ],
        ),
        _make_msg("tool", content="r1" * 80, tool_name="read_file"),
        _make_msg("tool", content="r2" * 80, tool_name="grep"),
    ]
    chunks = _split_into_chunks(messages, target_size=100)

    # All four messages (user, assistant, tool1, tool2) must be in one chunk.
    assert len(chunks) == 1, (
        f"Expected 1 chunk, got {len(chunks)} — "
        f"second tool result was split from its assistant"
    )
    assert len(chunks[0]) == 4
    assert chunks[0][0]["role"] == "user"
    assert chunks[0][1]["role"] == "assistant"
    assert chunks[0][2]["role"] == "tool"
    assert chunks[0][3]["role"] == "tool"


@pytest.mark.unit
def test_tool_result_chain_not_split():
    """A chain of 5 tool results from one assistant all stay together."""
    tool_names = ["t1", "t2", "t3", "t4", "t5"]
    messages = [
        _make_msg("user", "x" * 80),
        _make_msg(
            "assistant",
            content="",
            tool_calls=[
                {"function": {"name": name, "arguments": "{}"}}
                for name in tool_names
            ],
        ),
    ]
    for name in tool_names:
        messages.append(
            _make_msg("tool", content=f"result_{name}" * 20, tool_name=name)
        )

    chunks = _split_into_chunks(messages, target_size=100)

    # All 7 messages (user + assistant + 5 tool results) must be in one chunk.
    assert len(chunks) == 1, (
        f"Expected 1 chunk, got {len(chunks)} — "
        f"tool result chain was split"
    )
    assert len(chunks[0]) == 7
    assert chunks[0][0]["role"] == "user"
    assert chunks[0][1]["role"] == "assistant"
    # Verify all 5 tool results are present and in order
    tool_roles = [m["role"] for m in chunks[0][2:]]
    assert tool_roles == ["tool"] * 5
