"""Processing pipeline for structured DOM snapshots.

Transforms raw node data from the JS walker into the annotated text
format the agent expects (``[ref] [role] name`` lines mixed with text content).

Pipeline stages:
1. ``parse_nodes()`` — dict → DomNode
2. ``_filter_viewport()`` — remove out-of-viewport nodes
3. ``_filter_scope()`` — narrow to a heading/container section
4. ``_render_lines()`` — DomNode → text lines
5. ``_apply_budget()`` — truncate at character budget
"""

from __future__ import annotations

from tools.browser.core._dom_nodes import (
    DomNode,
    NodeType,
    ViewportPosition,
    parse_nodes,
)
from tools.browser.core.site_filters import filter_for_site

# Roles that are meaningless without an accessible name (ARIA "name from content").
# All other interactive roles carry value/state and are actionable even nameless.
NAME_REQUIRED_ROLES = frozenset({
    "link", "button", "tab", "menuitem", "option", "treeitem"
})

__all__ = ["process_snapshot"]


def process_snapshot(
    raw_nodes: list[dict],
    *,
    url: str = "",
    scope_query: str | None = None,
    budget: int = 8000,
    name_limit: int = 150,
    full_page: bool = False,
) -> tuple[str, bool]:
    """Process structured DOM nodes into annotated text output.

    Args:
        raw_nodes: Raw node dicts from the JS walker.
        url: Current page URL, used for site-specific filtering.
        scope_query: Optional section name to scope to.
        budget: Character budget for the output.
        name_limit: Max length for displayed names.
        full_page: If True, include out-of-viewport nodes.

    Returns:
        Tuple of (annotated text content, whether output was truncated).
    """
    nodes = parse_nodes(raw_nodes)
    if not full_page:
        nodes = _filter_viewport(nodes)
    prefix = ""
    if scope_query:
        nodes, found = _filter_scope(nodes, scope_query)
        if not found:
            prefix = f'[scope "{scope_query}" not found, showing full page]\n'
    if url:
        nodes = filter_for_site(url, nodes)
    lines = _render_lines(nodes, name_limit=name_limit)
    content, truncated = _apply_budget(lines, budget=budget)
    return prefix + content, truncated


def _filter_viewport(nodes: list[DomNode]) -> list[DomNode]:
    """Remove nodes entirely outside the viewport.

    Keeps ``IN`` and ``CLIPPED`` nodes. Container start/end markers are
    kept if they are ``IN`` or ``CLIPPED`` — their children handle
    themselves.
    """
    return [n for n in nodes if n.viewport != ViewportPosition.OUT]


def _filter_scope(
    nodes: list[DomNode], query: str,
) -> tuple[list[DomNode], bool]:
    """Narrow nodes to those within a matching heading's container.

    Searches for a heading whose name contains ``query`` (case-insensitive).
    Walks backwards from the heading to find the enclosing
    ``container_start``, then keeps only nodes within that container
    (up to its matching ``container_end``).

    Returns the filtered list and whether the scope was found.
    """
    q = query.lower()

    # Find matching heading — prefer exact match, then substring
    exact_idx = None
    substr_idx = None
    for i, node in enumerate(nodes):
        if node.type != NodeType.HEADING:
            continue
        name = (node.name or "").lower()
        if not name:
            continue
        if name == q and exact_idx is None:
            exact_idx = i
        elif q in name and substr_idx is None:
            substr_idx = i

    heading_idx = exact_idx if exact_idx is not None else substr_idx
    if heading_idx is None:
        return nodes, False

    heading_depth = nodes[heading_idx].depth

    # Walk backwards to find enclosing container_start
    container_idx = heading_idx
    for i in range(heading_idx - 1, -1, -1):
        node = nodes[i]
        if node.type == NodeType.CONTAINER_START and node.depth < heading_depth:
            container_idx = i
            break

    # If we found a container_start, find its matching container_end
    if nodes[container_idx].type == NodeType.CONTAINER_START:
        container_depth = nodes[container_idx].depth
        end_idx = len(nodes)
        for i in range(container_idx + 1, len(nodes)):
            node = nodes[i]
            if (node.type == NodeType.CONTAINER_END
                    and node.depth == container_depth):
                end_idx = i + 1
                break
        return nodes[container_idx:end_idx], True

    # No container found — return from heading to next heading at same
    # or higher level, or end of nodes
    end_idx = len(nodes)
    for i in range(heading_idx + 1, len(nodes)):
        node = nodes[i]
        if node.type == NodeType.HEADING and node.depth <= heading_depth:
            end_idx = i
            break
    return nodes[heading_idx:end_idx], True


def _truncate(text: str, limit: int) -> str:
    """Truncate text to limit, adding ellipsis if truncated."""
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _render_lines(nodes: list[DomNode], *, name_limit: int) -> list[str]:
    """Convert DomNode list into formatted text lines."""
    lines: list[str] = []
    for node in nodes:
        line = _render_node(node, name_limit=name_limit)
        if line:
            lines.append(line)
    return lines


def _render_node(node: DomNode, *, name_limit: int) -> str | None:
    """Render a single DomNode to its text line representation."""
    t = node.type

    if t == NodeType.TEXT:
        text = (node.text or "").strip()
        if len(text) <= 1:
            return None
        return _truncate(text, 200)

    if t == NodeType.HEADING:
        name = (node.name or "").strip()
        if not name:
            return None
        level = node.level or ""
        return f"[h{level}] {_truncate(name, name_limit)}"

    if t == NodeType.IMAGE:
        name = (node.name or "").strip()
        if not name:
            return None
        return f"[img] {_truncate(name, name_limit)}"

    if t == NodeType.INTERACTIVE:
        role = node.role or "button"
        ref = node.ref
        name = (node.name or "").strip()
        value = (node.value or "").strip()

        # Roles that are meaningless without an accessible name are skipped
        if not name and role in NAME_REQUIRED_ROLES:
            return None

        name_display = _truncate(name, name_limit) if name else ""
        ref_prefix = f"[{ref}] " if ref is not None else ""

        if role in ("combobox",):
            parts = [f"{ref_prefix}[{role}]"]
            if name_display:
                parts.append(f" {name_display}")
            if value:
                parts.append(f" = {value}")
            return "".join(parts)

        if role in ("checkbox", "radio", "switch"):
            suffix = " (checked)" if node.checked else ""
            return f"{ref_prefix}[{role}] {name_display}{suffix}"

        if role in ("textbox", "searchbox", "spinbutton", "slider"):
            val_display = _truncate(value, name_limit) if value else ""
            suffix = f" = {val_display}" if val_display else ""
            if role == "slider" and node.extra:
                e = node.extra
                suffix += f" (range {e['min']:.0f}-{e['max']:.0f}, {e['width']}px wide)"
            return f"{ref_prefix}[{role}] {name_display}{suffix}"

        # Generic interactive: button, link, tab, menuitem, etc.
        parts = [f"{ref_prefix}[{role}]"]
        if name_display:
            parts.append(f" {name_display}")
        # Append ARIA state annotations
        if node.pressed is True:
            parts.append(" (pressed)")
        if node.expanded is True:
            parts.append(" (expanded)")
        elif node.expanded is False:
            parts.append(" (collapsed)")
        if node.selected is True:
            parts.append(" (selected)")
        return "".join(parts)

    # container_start / container_end — structural markers, no output
    return None


def _apply_budget(
    lines: list[str], *, budget: int,
) -> tuple[str, bool]:
    """Truncate output at character budget."""
    result: list[str] = []
    chars = 0
    truncated = False

    for line in lines:
        line_cost = len(line) + 1  # +1 for newline
        if chars + line_cost > budget:
            truncated = True
            break
        result.append(line)
        chars += line_cost

    return "\n".join(result), truncated
