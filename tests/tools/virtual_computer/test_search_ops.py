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


@pytest.mark.unit
def test_grep_default_excludes() -> None:
    """Test that default excludes are always applied."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            # Create files in directories that should be excluded by default
            make_dirs(".git/objects")
            make_dirs("node_modules/package")
            make_dirs("__pycache__")
            make_dirs("src")
            
            write_file(".git/config", "test content\n")
            write_file(".git/objects/abc123", "test content\n")
            write_file("node_modules/package/index.js", "test content\n")
            write_file("__pycache__/module.pyc", "test content\n")
            write_file("package.lock", "test content\n")
            write_file("src/main.py", "test content\n")
            
            # Search without any exclude_globs - should only find src/main.py
            r = grep("test content", regex=False)
            assert r.success
            assert len(r.matches) == 1
            assert r.matches[0].file_path.endswith("src/main.py")
            
            # Search with custom exclude_globs - should still exclude defaults
            r = grep("test content", exclude_globs=["src/*"], regex=False)
            assert r.success
            assert len(r.matches) == 0  # All files excluded (src/* + defaults)


@pytest.mark.unit
def test_grep_result_fields_success_case() -> None:
    """Test that all GrepResult fields are populated correctly in success case."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            make_dirs("src")
            write_file("src/test1.py", "import os\nfrom sys import path\n# comment\n")
            write_file("src/test2.py", "import json\nprint('hello')\n")
            
            # Search for 'import' - should find 3 matches
            result = grep("import", regex=False)
            
            # Verify GrepResult fields
            assert result.success is True
            assert result.error is None
            assert result.truncated is False
            assert result.searched_files == 2  # Should have searched 2 files
            assert len(result.matches) == 3  # 3 occurrences of "import"
            
            # Verify GrepMatch fields for first match
            match1 = result.matches[0]
            assert isinstance(match1.file_path, str)
            assert match1.file_path.endswith("test1.py") or match1.file_path.endswith("test2.py")
            assert isinstance(match1.line_number, int)
            assert match1.line_number >= 1
            assert isinstance(match1.line, str)
            assert "import" in match1.line
            assert isinstance(match1.start_col, int)
            assert isinstance(match1.end_col, int)
            assert match1.start_col >= 0
            assert match1.end_col > match1.start_col
            assert match1.line[match1.start_col:match1.end_col] == "import"


@pytest.mark.unit
def test_grep_result_fields_truncated_case() -> None:
    """Test GrepResult fields when results are truncated."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            # Create file with many matches
            content = "\n".join([f"line {i} with target word" for i in range(20)])
            write_file("many_matches.txt", content)
            
            # Search with low max_results to trigger truncation
            result = grep("target", regex=False, max_results=5)
            
            # Verify truncation fields
            assert result.success is True
            assert result.error is None
            assert result.truncated is True  # Should be truncated
            assert result.searched_files == 1
            assert len(result.matches) == 5  # Limited by max_results
            
            # Verify all matches have correct column positions
            for match in result.matches:
                assert match.start_col >= 0
                assert match.end_col == match.start_col + len("target")
                assert match.line[match.start_col:match.end_col] == "target"


@pytest.mark.unit
def test_grep_result_fields_no_matches() -> None:
    """Test GrepResult fields when no matches are found."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("empty_search.txt", "nothing to find here\n")
            
            result = grep("nonexistent", regex=False)
            
            # Verify fields for no-match case
            assert result.success is True
            assert result.error is None
            assert result.truncated is False
            assert result.searched_files == 1
            assert len(result.matches) == 0


@pytest.mark.unit
def test_grep_result_fields_error_case() -> None:
    """Test GrepResult fields when an error occurs."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            # Mock path resolution to simulate workspace not found
            with mock.patch("tools.virtual_computer.search_ops.resolve_under_home") as mock_resolve:
                mock_resolve.return_value = (Path("/nonexistent"), Path("/nonexistent"), ".")
                
                result = grep("test", regex=False)
                
                # Verify error case fields
                assert result.success is False
                assert result.error is not None
                assert "workspace not found" in result.error
                assert result.truncated is False
                assert result.searched_files == 0
                assert len(result.matches) == 0


@pytest.mark.unit
def test_grep_match_column_positions_regex() -> None:
    """Test that GrepMatch column positions are accurate for regex searches."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("regex_test.txt", "  function myFunc() {\n    return value;\n  }\n")
            
            # Search for word boundaries
            result = grep(r"\bfunction\b", regex=True)
            
            assert result.success
            assert len(result.matches) == 1
            
            match = result.matches[0]
            assert match.line_number == 1
            assert match.start_col == 2  # "function" starts at column 2
            assert match.end_col == 10   # "function" ends at column 10
            assert match.line[match.start_col:match.end_col] == "function"


@pytest.mark.unit
def test_grep_match_column_positions_case_insensitive() -> None:
    """Test GrepMatch column positions with case-insensitive search."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("case_test.txt", "Hello WORLD hello\n")
            
            # Case-insensitive search (default)
            result = grep("hello", regex=False, case_sensitive=False)
            
            assert result.success
            assert len(result.matches) == 2
            
            # First match should be "Hello" at start
            match1 = result.matches[0]
            assert match1.start_col == 0
            assert match1.end_col == 5
            assert match1.line[match1.start_col:match1.end_col] == "Hello"
            
            # Second match should be "hello" at end
            match2 = result.matches[1]
            assert match2.start_col == 12
            assert match2.end_col == 17
            assert match2.line[match2.start_col:match2.end_col] == "hello"


@pytest.mark.unit
def test_grep_searched_files_count_with_excludes() -> None:
    """Test that searched_files count is accurate when files are excluded."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            # Create files in both included and excluded directories
            make_dirs("src")
            make_dirs("__pycache__")  # Should be excluded by default
            
            write_file("src/main.py", "test content\n")
            write_file("src/utils.py", "test content\n")
            write_file("__pycache__/module.pyc", "test content\n")  # Should be excluded
            write_file("regular.txt", "test content\n")
            
            result = grep("test", regex=False)
            
            # Should only count files that were actually searched (not excluded)
            assert result.success
            assert result.searched_files == 3  # src/main.py, src/utils.py, regular.txt
            assert len(result.matches) == 3    # One match per non-excluded file


@pytest.mark.unit
def test_grep_match_line_contains_full_line() -> None:
    """Test that GrepMatch.line contains the entire line, not just the matched portion."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            # Create file with lines containing matches surrounded by other content
            content = """    def function_name(arg1, arg2):
        return some_value + another_value
    # This is a comment with function inside
if __name__ == "__main__":
    print("Hello World")"""
            write_file("test_lines.py", content)
            
            # Search for 'function' - should find 2 matches
            result = grep("function", regex=False)
            
            assert result.success
            assert len(result.matches) == 2
            
            # First match should be in the function definition line
            match1 = result.matches[0]
            assert match1.line == "    def function_name(arg1, arg2):"
            assert match1.line_number == 1
            assert match1.start_col == 8  # "function" starts at column 8
            assert match1.end_col == 16   # "function" ends at column 16
            assert match1.line[match1.start_col:match1.end_col] == "function"
            
            # Second match should be in the comment line
            match2 = result.matches[1]
            assert match2.line == "    # This is a comment with function inside"
            assert match2.line_number == 3
            assert match2.start_col == 29  # "function" starts at column 29 in comment
            assert match2.end_col == 37    # "function" ends at column 37
            assert match2.line[match2.start_col:match2.end_col] == "function"
            
            # Verify that the full line context is preserved, not just the match
            assert "def " in match1.line and "(arg1, arg2):" in match1.line
            assert "# This is a comment" in match2.line and " inside" in match2.line
