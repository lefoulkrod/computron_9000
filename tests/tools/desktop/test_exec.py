"""Unit tests for desktop exec helpers."""

import json
import struct

import pytest

from tools.desktop._exec import _strip_stream_headers


def _frame(stream_type: int, payload: bytes) -> bytes:
    """Build a single Docker/Podman stream frame."""
    return struct.pack(">B3xI", stream_type, len(payload)) + payload


class TestStripStreamHeaders:
    """Tests for _strip_stream_headers."""

    @pytest.mark.unit
    def test_passthrough_when_no_framing(self):
        """Plain text without framing headers passes through unchanged."""
        data = b'[{"role": "button", "label": "OK"}]'
        assert _strip_stream_headers(data) == data

    @pytest.mark.unit
    def test_single_frame(self):
        """A single stdout frame is unwrapped correctly."""
        payload = b'[{"role": "button"}]'
        framed = _frame(1, payload)
        assert _strip_stream_headers(framed) == payload

    @pytest.mark.unit
    def test_multiple_frames_concatenated(self):
        """Multiple frames are concatenated into a single payload."""
        part1 = b'[{"role": "button"'
        part2 = b', "label": "OK"}]'
        framed = _frame(1, part1) + _frame(1, part2)
        assert _strip_stream_headers(framed) == part1 + part2

    @pytest.mark.unit
    def test_printable_bytes_in_size_field(self):
        """Size field containing printable ASCII bytes is handled correctly.

        This is the bug that caused the original JSONDecodeError — when
        the payload size contains bytes in the printable ASCII range
        (e.g. 0x5B = '['), a naive isprintable() filter keeps them.
        """
        # Build a payload whose length encodes a printable byte in the
        # size field.  Size 0x035B = 859 has '[' (0x5B) as the low byte.
        payload = b"x" * 859
        framed = _frame(1, payload) + _frame(1, b"more")
        result = _strip_stream_headers(framed)
        assert result == payload + b"more"

    @pytest.mark.unit
    def test_realistic_a11y_tree(self):
        """A realistic multi-chunk a11y JSON tree is reassembled correctly."""
        tree = json.dumps(
            [{"role": "toggle button", "label": "Applications",
              "x": 0, "y": 0, "w": 102, "h": 27}] * 30,
        ).encode()
        # Split into two chunks at an arbitrary boundary.
        mid = len(tree) // 2
        framed = _frame(1, tree[:mid]) + _frame(1, tree[mid:])
        result = _strip_stream_headers(framed)
        assert json.loads(result) == json.loads(tree)

    @pytest.mark.unit
    def test_empty_input(self):
        """Empty bytes return empty bytes."""
        assert _strip_stream_headers(b"") == b""

    @pytest.mark.unit
    def test_stderr_frames_included(self):
        """Stderr frames (type 2) are also extracted."""
        payload = b"some stderr output"
        framed = _frame(2, payload)
        assert _strip_stream_headers(framed) == payload
