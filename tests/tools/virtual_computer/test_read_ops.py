"""Unit tests for read operations: read_file, head, tail.

Uses a temporary home_dir via config.load_config monkeypatch.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock
import tempfile

import pytest

from tools.virtual_computer.read_ops import head, read_file, tail
from tools.virtual_computer.file_ops import write_file


class DummyConfig:
	class VirtualComputer:
		def __init__(self, home_dir: str) -> None:
			self.home_dir = home_dir

	def __init__(self, home_dir: str) -> None:
		self.virtual_computer = self.VirtualComputer(home_dir)


@pytest.mark.unit
def test_read_file_full_and_range() -> None:
	with tempfile.TemporaryDirectory() as tmp_home:
		with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
			content = "one\n two\nthree\n"
			write_file("a.txt", content)
			full = read_file("a.txt")
			assert full.success and full.content == content
			r = read_file("a.txt", start=2, end=2)
			assert r.success and r.content == " two\n"


@pytest.mark.unit
def test_head_and_tail_defaults() -> None:
	with tempfile.TemporaryDirectory() as tmp_home:
		with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
			lines = "".join(f"L{i}\n" for i in range(1, 11))
			write_file("b.txt", lines)
			h = head("b.txt", n=3)
			assert h.success and h.content == "L1\nL2\nL3\n"
			t = tail("b.txt", n=2)
			# Standard tail semantics: last two lines when trailing newline present
			assert t.success and t.content == "L9\nL10\n"

