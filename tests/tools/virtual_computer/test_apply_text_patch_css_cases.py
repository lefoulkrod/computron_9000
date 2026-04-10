"""CSS-focused tests for apply_text_patch (old_text/new_text unique-match).

These tests validate that:
- Replacing a unique CSS block succeeds and generates a well-formed diff.
- Multi-line replacements (property + brace) work correctly.
- Replacing a specific property only changes that property.
- Non-matching text returns a descriptive error.
"""

from pathlib import Path
import tempfile
import pytest

from tools.virtual_computer.patching import apply_text_patch
from tools.virtual_computer.file_ops import write_file


@pytest.mark.unit
def test_css_replace_brace_with_property() -> None:
    """Replacing a closing brace with a property should produce clean diff."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "style.css")
        css = ".window:hover {\n}\n/* tail */\n"
        write_file(target, css)

        res = apply_text_patch(
            target,
            old_text=".window:hover {\n}",
            new_text=".window:hover {\n  box-shadow: 0 4px 15px rgba(0, 0, 0, 20%);\n}",
        )
        assert res.success, res.error

        content = Path(target).read_text(encoding="utf-8")
        assert "box-shadow: 0 4px 15px rgba(0, 0, 0, 20%);" in content
        assert "/* tail */" in content


@pytest.mark.unit
def test_css_replace_specific_property_only() -> None:
    """Replacing one property should not alter adjacent properties."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "style.css")
        css = (
            "body {\n"
            "  background: white;\n"
            "  border: 1px solid #ccc;\n"
            "  box-shadow: 0 2px 10px rgba(0,0,0,10%);\n"
            "  margin: 1rem;\n"
            "}\n"
        )
        write_file(target, css)

        res = apply_text_patch(
            target,
            old_text="  box-shadow: 0 2px 10px rgba(0,0,0,10%);",
            new_text="  box-shadow: 0 2px 10px rgba(0, 0, 0, 10%);",
        )
        assert res.success, res.error

        content = Path(target).read_text(encoding="utf-8")
        assert "  box-shadow: 0 2px 10px rgba(0, 0, 0, 10%);\n" in content
        assert "  margin: 1rem;\n" in content
        assert "  border: 1px solid #ccc;\n" in content


@pytest.mark.unit
def test_css_no_match_returns_error() -> None:
    """Non-matching text returns descriptive error."""
    with tempfile.TemporaryDirectory() as tmp_home:
        target = str(Path(tmp_home) / "style.css")
        write_file(target, "body { color: red; }\n")
        res = apply_text_patch(
            target,
            old_text="color: blue;",
            new_text="color: green;",
        )
        assert not res.success
        assert "No match found" in (res.error or "")
