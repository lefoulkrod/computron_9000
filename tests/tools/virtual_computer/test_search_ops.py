"""Unit tests for search_ops.grep."""

from __future__ import annotations

from pathlib import Path
from unittest import mock
import tempfile

import pytest

from tools.virtual_computer.search_ops import grep
from tools.virtual_computer.file_ops import write_file, make_dirs


class DummyConfig:
    class VirtualComputer:
        def __init__(self, home_dir: str) -> None:
            self.home_dir = home_dir

    def __init__(self, home_dir: str) -> None:
        self.virtual_computer = self.VirtualComputer(home_dir)


@pytest.mark.unit
def test_grep_literal_and_regex_and_globs() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            make_dirs("src")
            write_file("src/a.txt", "hello world\nHello again\n")
            write_file("src/b.md", "hello md\n")
            # literal, case-insensitive default
            r1 = grep("hello", include_globs=["src/*.txt"], regex=False)
            assert r1.success and len(r1.matches) == 2
            # literal, case-sensitive
            r1_cs = grep("hello", include_globs=["src/*.txt"], regex=False, case_sensitive=True)
            assert r1_cs.success and len(r1_cs.matches) == 1
            # regex, case sensitive
            r2 = grep("^Hello", include_globs=["src/*"], regex=True, case_sensitive=True)
            assert r2.success and any(m.line.startswith("Hello") for m in r2.matches)


@pytest.mark.unit
def test_grep_truncates_on_max_results() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("many.txt", "\n".join(["hit" for _ in range(50)]))
            r = grep("hit", regex=False, max_results=10)
            assert r.success and r.truncated and len(r.matches) == 10


@pytest.mark.unit
def test_grep_anchors() -> None:
    """Anchors are interpreted per-line since we search line-by-line."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("anch.txt", "alpha\nbeta\nGamma\n")
            r = grep(r"^beta$", regex=True, case_sensitive=True)
            assert r.success and len(r.matches) == 1
            m = r.matches[0]
            assert m.line == "beta" and m.line_number == 2


@pytest.mark.unit
def test_grep_exclude_globs() -> None:
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            make_dirs("src")
            write_file("src/a.txt", "hello world\n")
            write_file("src/b.md", "hello md\n")
            # Include both files, but exclude markdown; expect only .txt match
            r = grep("hello", include_globs=["src/*"], exclude_globs=["*.md"], regex=False)
            assert r.success
            assert all(m.file_path.endswith("a.txt") for m in r.matches)
