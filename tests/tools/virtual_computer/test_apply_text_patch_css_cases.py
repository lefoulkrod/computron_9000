"""CSS-focused tests for apply_text_patch mirroring console log scenarios.

These tests validate that:
- Replacing a closing brace line with a property generates a well-formed diff
  (separate - and + lines; no merged "-}+" artifact) and updates content accordingly.
- Replacing a closing brace line with a multi-line replacement (property + brace)
  succeeds and yields expected unified diff output.
- Replacing a specific property line only changes that line and does not introduce
  unrelated modifications to adjacent lines.
- An out-of-range line replacement returns an "Invalid line range" error.
"""

from pathlib import Path
from unittest import mock
import tempfile
import pytest

from tools.virtual_computer.patching import apply_text_patch
from tools.virtual_computer.file_ops import write_file


class DummyConfig:
    class VirtualComputer:
        def __init__(self, home_dir: str) -> None:
            self.home_dir = home_dir

    def __init__(self, home_dir: str) -> None:
        self.virtual_computer = self.VirtualComputer(home_dir)


@pytest.mark.unit
def test_css_replace_brace_line_with_property_produces_separate_diff_lines() -> None:
    """Replacing '}' line with a property should remove the brace and add only the property.

    Verifies the unified diff uses separate lines for removals and additions (no "-}+" merge)
    and that the file content reflects the change.
    """
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            # Construct a file where line 44 is an opening brace and line 45 is the closing brace.
            pad = [f"/* line {i} */\n" for i in range(1, 44)]  # lines 1..43
            content = "".join(pad + [
                ".window:hover {\n",  # line 44
                "}\n",                   # line 45 (to be replaced)
                "/* tail */\n",          # line 46
            ])
            write_file("webos/css/style.css", content)

            replacement = "  box-shadow: 0 4px 15px rgba(0, 0, 0, 20%);\n"
            res = apply_text_patch(
                "webos/css/style.css", start_line=45, end_line=45, replacement=replacement
            )
            assert res.success, res.error
            assert res.file_path == "webos/css/style.css"
            # Headers present, diff hunks sane
            assert res.diff is not None
            assert res.diff.startswith("--- webos/css/style.css (before)\n+++ webos/css/style.css (after)\n@@ ")
            # Ensure removal and addition are on separate lines
            assert "-}\n" in res.diff
            assert "+  box-shadow: 0 4px 15px rgba(0, 0, 0, 20%);\n" in res.diff
            assert "-}+" not in res.diff  # no merged removal+addition

            # File content should now have lost the closing brace at that spot
            new_text = Path(tmp_home, "webos/css/style.css").read_text(encoding="utf-8")
            assert "}\n" not in new_text.splitlines(keepends=True)[44]  # index 44 == original line 45


@pytest.mark.unit
def test_css_replace_brace_line_with_property_and_brace_multiline() -> None:
    """Replacing '}' with two lines (property + brace) should succeed and format diff correctly."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            pad = [f"/* line {i} */\n" for i in range(1, 44)]
            content = "".join(pad + [
                ".window:hover {\n",  # 44
                "}\n",                   # 45
                "/* tail */\n",          # 46
            ])
            write_file("webos/css/style.css", content)

            replacement = "  box-shadow: 0 4px 15px rgba(0, 0, 0, 20%);\n}\n"
            res = apply_text_patch(
                "webos/css/style.css", start_line=45, end_line=45, replacement=replacement
            )
            assert res.success, res.error
            assert res.file_path == "webos/css/style.css"
            # Diff shows the property line added; brace may be aligned as unchanged context by difflib
            assert res.diff is not None
            assert "+  box-shadow: 0 4px 15px rgba(0, 0, 0, 20%);\n" in res.diff

            # Verify file content now includes property then brace at positions 45 and 46 (1-based)
            lines = Path(tmp_home, "webos/css/style.css").read_text(encoding="utf-8").splitlines()
            assert lines[44] == "  box-shadow: 0 4px 15px rgba(0, 0, 0, 20%);"  # line 45
            assert lines[45] == "}"  # line 46


@pytest.mark.unit
def test_css_replace_specific_property_line_only_changes_that_line() -> None:
    """Replacing one property line should not alter adjacent properties in the diff or file."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            css = (
                "body {\n"
                "  background: white;\n"
                "  border: 1px solid #ccc;\n"
                "  border-radius: 4px;\n"
                "  box-shadow: 0 2px 10px rgba(0,0,0,10%);\n"
                "  margin: 1rem;\n"
                "  display: grid;\n"
                "  grid-template-columns: 1fr;\n"
                "}\n"
            )
            write_file("webos/css/style.css", css)

            # Replace only the box-shadow line
            res = apply_text_patch(
                "webos/css/style.css",
                start_line=5,
                end_line=5,
                replacement="  box-shadow: 0 2px 10px rgba(0, 0, 0, 10%);\n",
            )
            assert res.success, res.error

            # Exactly one removed and one added line in the hunk
            # (exclude headers which also start with +++)
            assert res.diff is not None
            removed = [ln for ln in res.diff.splitlines() if ln.startswith("-") and not ln.startswith("--- ")]
            added = [ln for ln in res.diff.splitlines() if ln.startswith("+") and not ln.startswith("+++ ")]
            assert len(removed) == 1
            assert len(added) == 1
            assert removed[0] == "-  box-shadow: 0 2px 10px rgba(0,0,0,10%);"
            assert added[0] == "+  box-shadow: 0 2px 10px rgba(0, 0, 0, 10%);"

            # Adjacent properties remain unchanged in the resulting file
            content = Path(tmp_home, "webos/css/style.css").read_text(encoding="utf-8")
            assert "  margin: 1rem;\n" in content
            assert "  display: grid;\n" in content


@pytest.mark.unit
def test_apply_text_patch_invalid_range_when_line_number_too_large() -> None:
    """Out-of-range (e.g., line 45 in short file) returns Invalid line range and no diff."""
    with tempfile.TemporaryDirectory() as tmp_home:
        with mock.patch("config.load_config", return_value=DummyConfig(tmp_home)):
            write_file("webos/css/style.css", "a\n" * 10)  # only 10 lines
            res = apply_text_patch(
                "webos/css/style.css",
                start_line=45,
                end_line=45,
                replacement="  box-shadow: 0 4px 15px rgba(0, 0, 0, 20%);\n",
            )
            assert not res.success
            assert res.error == "Invalid line range"
            assert res.diff is None
