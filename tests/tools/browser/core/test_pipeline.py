"""Tests for the DOM snapshot processing pipeline."""

import pytest

from tools.browser.core._pipeline import (
    _apply_budget,
    _filter_scope,
    _filter_viewport,
    _render_lines,
    _render_node,
    process_snapshot,
)
from tools.browser.core._dom_nodes import DomNode, NodeType, ViewportPosition, parse_nodes


# -- Helpers for building test nodes --

def _text(text, *, depth=0, viewport="in"):
    return {"type": "text", "depth": depth, "text": text, "viewport": viewport}

def _heading(name, level, *, depth=0, viewport="in"):
    return {"type": "heading", "depth": depth, "name": name, "level": level, "viewport": viewport}

def _interactive(role, name, *, ref=None, depth=0, viewport="in", value="", checked=None,
                 expanded=None, selected=None, pressed=None):
    d = {
        "type": "interactive", "depth": depth, "role": role, "name": name,
        "value": value, "viewport": viewport, "checked": checked,
        "expanded": expanded, "selected": selected, "pressed": pressed,
    }
    if ref is not None:
        d["ref"] = ref
    return d

def _image(name, *, depth=0, viewport="in"):
    return {"type": "image", "depth": depth, "name": name, "viewport": viewport}

def _container_start(tag="TABLE", *, depth=0, viewport="in", role=None):
    d = {"type": "container_start", "depth": depth, "tag": tag, "viewport": viewport}
    if role:
        d["role"] = role
    return d

def _container_end(tag="TABLE", *, depth=0, viewport="in", role=None):
    d = {"type": "container_end", "depth": depth, "tag": tag, "viewport": viewport}
    if role:
        d["role"] = role
    return d


@pytest.mark.unit
class TestFilterViewport:
    """Viewport filtering removes out-of-viewport nodes."""

    def test_keeps_in_and_clipped(self):
        """Nodes with viewport IN or CLIPPED are kept."""
        nodes = parse_nodes([
            _text("visible", viewport="in"),
            _text("clipped", viewport="clipped"),
            _text("hidden", viewport="out"),
        ])
        filtered = _filter_viewport(nodes)
        assert len(filtered) == 2
        assert filtered[0].text == "visible"
        assert filtered[1].text == "clipped"

    def test_empty_list(self):
        """Empty input returns empty output."""
        assert _filter_viewport([]) == []


@pytest.mark.unit
class TestFilterScope:
    """Scope filtering narrows to a heading's container."""

    def test_exact_heading_match(self):
        """Exact heading match scopes to its container."""
        nodes = parse_nodes([
            _heading("Page Title", 1, depth=0),
            _text("Intro text", depth=1),
            _container_start("SECTION", depth=1),
            _heading("Target Section", 2, depth=2),
            _text("Section content", depth=3),
            _interactive("button", "Action", depth=3),
            _container_end("SECTION", depth=1),
            _text("After section", depth=1),
        ])
        filtered, found = _filter_scope(nodes, "Target Section")
        assert found is True
        # Should include container_start through container_end
        types = [n.type for n in filtered]
        assert NodeType.CONTAINER_START in types
        assert NodeType.CONTAINER_END in types
        # After-section text should be excluded
        texts = [n.text for n in filtered if n.text]
        assert "After section" not in texts
        assert "Section content" in texts

    def test_substring_match(self):
        """Substring heading match works as fallback."""
        nodes = parse_nodes([
            _heading("My Important Section", 2, depth=0),
            _text("Content here", depth=1),
        ])
        filtered, found = _filter_scope(nodes, "Important")
        assert found is True
        assert len(filtered) >= 1

    def test_scope_not_found(self):
        """Missing scope returns all nodes and found=False."""
        nodes = parse_nodes([
            _heading("Title", 1, depth=0),
            _text("Body", depth=1),
        ])
        filtered, found = _filter_scope(nodes, "Nonexistent")
        assert found is False
        assert len(filtered) == 2

    def test_exact_match_preferred_over_substring(self):
        """Exact match wins over substring match."""
        nodes = parse_nodes([
            _heading("Results", 2, depth=0),
            _text("Exact match content", depth=1),
            _heading("Search Results Summary", 2, depth=0),
            _text("Substring match content", depth=1),
        ])
        filtered, found = _filter_scope(nodes, "Results")
        assert found is True
        # Should scope to exact match heading
        assert any(n.text == "Exact match content" for n in filtered)

    def test_heading_without_container(self):
        """When no container_start exists, scopes from heading to next heading."""
        nodes = parse_nodes([
            _heading("Section A", 2, depth=0),
            _text("Content A", depth=1),
            _heading("Section B", 2, depth=0),
            _text("Content B", depth=1),
        ])
        filtered, found = _filter_scope(nodes, "Section A")
        assert found is True
        texts = [n.text for n in filtered if n.text]
        assert "Content A" in texts
        assert "Content B" not in texts


@pytest.mark.unit
class TestRenderNode:
    """Individual node rendering."""

    def test_text_node(self):
        node = DomNode(type=NodeType.TEXT, depth=0, text="Hello world")
        assert _render_node(node, name_limit=150) == "Hello world"

    def test_text_node_short_ignored(self):
        """Single character text nodes are filtered out."""
        node = DomNode(type=NodeType.TEXT, depth=0, text="x")
        assert _render_node(node, name_limit=150) is None

    def test_text_node_truncated(self):
        """Long text is truncated at 200 chars."""
        long_text = "a" * 250
        node = DomNode(type=NodeType.TEXT, depth=0, text=long_text)
        result = _render_node(node, name_limit=150)
        assert len(result) == 203  # 200 + "..."
        assert result.endswith("...")

    def test_heading(self):
        node = DomNode(type=NodeType.HEADING, depth=0, name="Page Title", level=1)
        assert _render_node(node, name_limit=150) == "[h1] Page Title"

    def test_heading_name_truncated(self):
        """Heading names respect name_limit."""
        node = DomNode(type=NodeType.HEADING, depth=0, name="A" * 200, level=2)
        result = _render_node(node, name_limit=20)
        assert result == "[h2] " + "A" * 20 + "..."

    def test_button(self):
        node = DomNode(type=NodeType.INTERACTIVE, depth=0, role="button", name="Submit")
        assert _render_node(node, name_limit=150) == "[button] Submit"

    def test_link(self):
        node = DomNode(type=NodeType.INTERACTIVE, depth=0, role="link", name="Home")
        assert _render_node(node, name_limit=150) == "[link] Home"

    def test_checkbox_checked(self):
        node = DomNode(type=NodeType.INTERACTIVE, depth=0, role="checkbox", name="Agree", checked=True)
        assert _render_node(node, name_limit=150) == "[checkbox] Agree (checked)"

    def test_checkbox_unchecked(self):
        node = DomNode(type=NodeType.INTERACTIVE, depth=0, role="checkbox", name="Agree", checked=False)
        assert _render_node(node, name_limit=150) == "[checkbox] Agree"

    def test_textbox_with_value(self):
        node = DomNode(type=NodeType.INTERACTIVE, depth=0, role="textbox", name="Email", value="a@b.com")
        assert _render_node(node, name_limit=150) == "[textbox] Email = a@b.com"

    def test_textbox_empty_value(self):
        node = DomNode(type=NodeType.INTERACTIVE, depth=0, role="textbox", name="Email", value="")
        assert _render_node(node, name_limit=150) == "[textbox] Email"

    def test_combobox_with_value(self):
        node = DomNode(type=NodeType.INTERACTIVE, depth=0, role="combobox", name="Country", value="US")
        assert _render_node(node, name_limit=150) == "[combobox] Country = US"

    def test_combobox_nameless(self):
        """Nameless combobox still renders."""
        node = DomNode(type=NodeType.INTERACTIVE, depth=0, role="combobox", name="", value="Option 1")
        assert _render_node(node, name_limit=150) == "[combobox] = Option 1"

    def test_nameless_button_filtered(self):
        """Buttons without names are filtered out."""
        node = DomNode(type=NodeType.INTERACTIVE, depth=0, role="button", name="")
        assert _render_node(node, name_limit=150) is None

    def test_image(self):
        node = DomNode(type=NodeType.IMAGE, depth=0, name="Logo")
        assert _render_node(node, name_limit=150) == "[img] Logo"

    def test_image_no_alt(self):
        """Images without alt text are filtered."""
        node = DomNode(type=NodeType.IMAGE, depth=0, name="")
        assert _render_node(node, name_limit=150) is None

    def test_container_markers_no_output(self):
        """Container start/end produce no output lines."""
        start = DomNode(type=NodeType.CONTAINER_START, depth=0, tag="TABLE")
        end = DomNode(type=NodeType.CONTAINER_END, depth=0, tag="TABLE")
        assert _render_node(start, name_limit=150) is None
        assert _render_node(end, name_limit=150) is None

    def test_button_pressed(self):
        node = DomNode(type=NodeType.INTERACTIVE, depth=0, role="button", name="Toggle", pressed=True)
        assert _render_node(node, name_limit=150) == "[button] Toggle (pressed)"

    def test_tab_selected(self):
        node = DomNode(type=NodeType.INTERACTIVE, depth=0, role="tab", name="Details", selected=True)
        assert _render_node(node, name_limit=150) == "[tab] Details (selected)"

    def test_button_expanded(self):
        node = DomNode(type=NodeType.INTERACTIVE, depth=0, role="button", name="Menu", expanded=True)
        assert _render_node(node, name_limit=150) == "[button] Menu (expanded)"

    def test_button_collapsed(self):
        node = DomNode(type=NodeType.INTERACTIVE, depth=0, role="button", name="Menu", expanded=False)
        assert _render_node(node, name_limit=150) == "[button] Menu (collapsed)"


@pytest.mark.unit
class TestApplyBudget:
    """Budget enforcement."""

    def test_preserves_duplicate_lines(self):
        """Repeated lines are kept (no dedup)."""
        lines = ["Hello", "World", "Hello", "World", "Unique"]
        content, truncated = _apply_budget(lines, budget=8000)
        assert content == "Hello\nWorld\nHello\nWorld\nUnique"
        assert truncated is False

    def test_truncates_at_budget(self):
        """Output is truncated when budget is exceeded."""
        lines = [f"Line {i}" for i in range(100)]
        content, truncated = _apply_budget(lines, budget=50)
        assert truncated is True
        assert len(content) <= 50

    def test_empty_input(self):
        content, truncated = _apply_budget([], budget=8000)
        assert content == ""
        assert truncated is False

    def test_exact_budget(self):
        """Lines that exactly fill the budget are not truncated."""
        # "ab" + newline = 3 chars each
        lines = ["ab", "cd"]
        content, truncated = _apply_budget(lines, budget=6)
        assert content == "ab\ncd"
        assert truncated is False


@pytest.mark.unit
class TestProcessSnapshot:
    """End-to-end pipeline tests."""

    def test_basic_page(self):
        """A simple page with heading, text, and button."""
        raw = [
            _heading("Welcome", 1),
            _text("Hello world"),
            _interactive("button", "Click me"),
            _interactive("link", "Learn more"),
        ]
        content, truncated = process_snapshot(raw, budget=8000)
        assert "[h1] Welcome" in content
        assert "Hello world" in content
        assert "[button] Click me" in content
        assert "[link] Learn more" in content
        assert truncated is False

    def test_viewport_filtering(self):
        """Out-of-viewport nodes are removed when not full_page."""
        raw = [
            _text("Visible text", viewport="in"),
            _text("Hidden text", viewport="out"),
            _interactive("button", "Hidden button", viewport="out"),
        ]
        content, truncated = process_snapshot(raw, budget=8000)
        assert "Visible text" in content
        assert "Hidden text" not in content
        assert "Hidden button" not in content

    def test_full_page_keeps_all(self):
        """full_page=True keeps out-of-viewport nodes."""
        raw = [
            _text("Visible", viewport="in"),
            _text("Below fold", viewport="out"),
        ]
        content, truncated = process_snapshot(raw, budget=8000, full_page=True)
        assert "Visible" in content
        assert "Below fold" in content

    def test_scope_filtering(self):
        """Scope query narrows output to matching section."""
        raw = [
            _heading("Header", 1, depth=0),
            _text("Intro", depth=1),
            _container_start("SECTION", depth=1),
            _heading("Results", 2, depth=2),
            _text("Result content", depth=3),
            _container_end("SECTION", depth=1),
            _text("Footer", depth=1),
        ]
        content, truncated = process_snapshot(raw, scope_query="Results", budget=8000)
        assert "Result content" in content
        assert "Footer" not in content
        assert "Intro" not in content

    def test_scope_not_found_prefix(self):
        """Missing scope adds warning prefix."""
        raw = [_text("Some text")]
        content, truncated = process_snapshot(raw, scope_query="Missing", budget=8000)
        assert '[scope "Missing" not found, showing full page]' in content
        assert "Some text" in content

    def test_budget_truncation(self):
        """Large output is truncated at budget."""
        raw = [_text(f"Line number {i} with some padding text") for i in range(200)]
        content, truncated = process_snapshot(raw, budget=500)
        assert truncated is True
        assert len(content) <= 500

    def test_duplicates_preserved(self):
        """Duplicate text lines are kept (no dedup)."""
        raw = [
            _text("Repeated line"),
            _text("Repeated line"),
            _text("Unique line"),
        ]
        content, truncated = process_snapshot(raw, budget=8000)
        assert content.count("Repeated line") == 2
        assert "Unique line" in content

    def test_checkbox_state(self):
        """Checkbox state renders correctly."""
        raw = [
            _interactive("checkbox", "Option A", checked=True),
            _interactive("checkbox", "Option B", checked=False),
        ]
        content, truncated = process_snapshot(raw, budget=8000)
        assert "[checkbox] Option A (checked)" in content
        assert "[checkbox] Option B" in content
        assert "Option B (checked)" not in content

    def test_textbox_with_value(self):
        """Textbox shows current value."""
        raw = [_interactive("textbox", "Username", value="john")]
        content, truncated = process_snapshot(raw, budget=8000)
        assert "[textbox] Username = john" in content

    def test_empty_nodes(self):
        """Empty input produces empty output."""
        content, truncated = process_snapshot([], budget=8000)
        assert content == ""
        assert truncated is False

    def test_aria_states(self):
        """ARIA states (expanded, selected, pressed) render correctly."""
        raw = [
            _interactive("button", "Menu", expanded=True),
            _interactive("tab", "Tab 1", selected=True),
            _interactive("button", "Toggle", pressed=True),
        ]
        content, truncated = process_snapshot(raw, budget=8000)
        assert "[button] Menu (expanded)" in content
        assert "[tab] Tab 1 (selected)" in content
        assert "[button] Toggle (pressed)" in content

    def test_ref_prefix_on_interactive_nodes(self):
        """Interactive nodes with refs render as [ref] [role] name."""
        raw = [
            _interactive("button", "Add to Cart", ref=7),
            _interactive("link", "Home", ref=8),
            _interactive("textbox", "Search", ref=9, value="query"),
        ]
        content, truncated = process_snapshot(raw, budget=8000)
        assert "[7] [button] Add to Cart" in content
        assert "[8] [link] Home" in content
        assert "[9] [textbox] Search = query" in content

    def test_ref_prefix_on_checkbox(self):
        """Checkbox with ref renders as [ref] [checkbox] name (checked)."""
        raw = [_interactive("checkbox", "Remember me", ref=3, checked=True)]
        content, truncated = process_snapshot(raw, budget=8000)
        assert "[3] [checkbox] Remember me (checked)" in content

    def test_ref_prefix_on_combobox(self):
        """Combobox with ref renders as [ref] [combobox] name = value."""
        raw = [_interactive("combobox", "Sort by", ref=5, value="Price")]
        content, truncated = process_snapshot(raw, budget=8000)
        assert "[5] [combobox] Sort by = Price" in content

    def test_no_ref_prefix_when_ref_missing(self):
        """Nodes without ref render without prefix (backwards compat)."""
        raw = [_interactive("button", "Submit")]
        content, truncated = process_snapshot(raw, budget=8000)
        assert content.strip() == "[button] Submit"
