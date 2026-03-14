"""Amazon site filter — strips navigation chrome, noise, and footer."""

from __future__ import annotations

from tools.browser.core._dom_nodes import DomNode, NodeType

_DROP_BUTTONS = frozenset({
    "leave feedback on sponsored ad",
    "join prime",
    "play sponsored video",
    "back to top",
})

# Headings that mark the start of sections to truncate (everything from
# this heading onward is dropped).
_FOOTER_HEADINGS = frozenset({
    "get to know us",
    "make money with us",
    "amazon payment products",
    "let us help you",
    "see personalized recommendations",
    "your items",
})

# Text fragments that indicate noise lines (case-insensitive substring match)
_DROP_TEXT = (
    "enjoy fast, free delivery, exclusive deals",
    "product summary presents key product information",
    "keyboard shortcut",
    "get fast, free shipping with",
)


def _is_noise(node: DomNode) -> bool:
    """Return True for Amazon-specific noise nodes."""
    name_lower = (node.name or "").strip().lower()
    text_lower = (node.text or "").strip().lower()

    # Sponsored/Prime/feedback buttons
    if node.type == NodeType.INTERACTIVE and node.role == "button":
        if name_lower in _DROP_BUTTONS:
            return True
        if name_lower.startswith("sponsored"):
            return True

    # Prime logo images
    if node.type == NodeType.IMAGE and "prime" in name_lower:
        return True

    # Noise text lines
    if node.type == NodeType.TEXT:
        for frag in _DROP_TEXT:
            if frag in text_lower:
                return True

    # Accessibility-hint headings that aren't real content
    if node.type == NodeType.HEADING:
        if "product summary presents" in name_lower:
            return True

    return False


def filter_amazon(nodes: list[DomNode]) -> list[DomNode]:
    """Strip Amazon navigation chrome and noise from the node list.

    Phase 1: Keep searchbox + Go button, drop everything else before the
    first real heading.
    Phase 2: Remove known noise nodes (Prime upsells, sponsored buttons,
    accessibility hints).
    Phase 3: Truncate at footer / "Your Items" sections.
    """
    # --- Phase 1: strip nav ---
    after_nav: list[DomNode] = []
    found_first_heading = False

    i = 0
    while i < len(nodes):
        node = nodes[i]

        if found_first_heading:
            after_nav.append(node)
            i += 1
            continue

        # Keep the searchbox and the Go button immediately after it
        if (node.type == NodeType.INTERACTIVE
                and node.role in ("searchbox", "textbox")
                and "search" in (node.name or "").lower()):
            after_nav.append(node)
            if i + 1 < len(nodes):
                nxt = nodes[i + 1]
                if (nxt.type == NodeType.INTERACTIVE
                        and nxt.role == "button"
                        and (nxt.name or "").strip().lower() == "go"):
                    after_nav.append(nxt)
                    i += 2
                    continue
            i += 1
            continue

        if node.type == NodeType.HEADING:
            found_first_heading = True
            after_nav.append(node)
            i += 1
            continue

        i += 1

    # If no heading was found, we've scrolled past the nav — use all nodes
    if not found_first_heading:
        after_nav = nodes

    # --- Phase 2: remove noise nodes ---
    cleaned = [n for n in after_nav if not _is_noise(n)]

    # --- Phase 3: truncate at footer / "Your Items" sections ---
    result: list[DomNode] = []
    for node in cleaned:
        if node.type == NodeType.HEADING:
            name_lower = (node.name or "").strip().lower()
            if name_lower in _FOOTER_HEADINGS:
                break
        result.append(node)

    return result
