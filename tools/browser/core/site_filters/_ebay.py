"""eBay site filter — strips navigation chrome, category tree, and footer."""

from __future__ import annotations

from tools.browser.core._dom_nodes import DomNode, NodeType

# Category tree headings to skip (drop heading + children until next h3).
_SKIP_SECTIONS = frozenset({
    "category",
})

_FOOTER_HEADINGS = frozenset({
    "shop on ebay",
    "about ebay",
    "buy",
    "sell",
    "stay connected",
    "help & contact",
    "trending auctions",
})

_DROP_BUTTONS = frozenset({
    "advertisement",
})


def filter_ebay(nodes: list[DomNode]) -> list[DomNode]:
    """Strip eBay navigation chrome, category tree, and footer.

    Phase 1: Keep search bar + Search button, drop everything else
    before the first ``[h2] Filter`` or ``[h1]`` heading.
    Phase 2: Drop the category tree section while keeping other
    sidebar filters (Brand, Shipping, Price, etc.).
    Phase 3: Drop ad buttons and footer sections.
    """
    # --- Phase 1: strip top nav, keep search bar ---
    after_nav: list[DomNode] = []
    found_content = False

    i = 0
    while i < len(nodes):
        node = nodes[i]

        if found_content:
            after_nav.append(node)
            i += 1
            continue

        # Keep the search combobox/textbox and Search button
        if (node.type == NodeType.INTERACTIVE
                and node.role in ("combobox", "searchbox", "textbox")
                and "search" in (node.name or "").lower()):
            after_nav.append(node)
            # Grab the Search button that follows nearby
            for j in range(i + 1, min(i + 4, len(nodes))):
                nxt = nodes[j]
                if (nxt.type == NodeType.INTERACTIVE
                        and nxt.role == "button"
                        and (nxt.name or "").strip().lower() == "search"):
                    after_nav.append(nxt)
                    break
            i += 1
            continue

        # h1 or h2 marks start of real content (sidebar + results)
        if node.type == NodeType.HEADING and node.level in (1, 2):
            found_content = True
            after_nav.append(node)
            i += 1
            continue

        i += 1

    # If no nav marker was found, we've scrolled past it — use all nodes
    if not found_content:
        after_nav = nodes

    # --- Phase 2: drop category tree section ---
    result: list[DomNode] = []
    skip_until_next_h3 = False

    for node in after_nav:
        if node.type == NodeType.HEADING:
            name_lower = (node.name or "").strip().lower()
            if name_lower in _SKIP_SECTIONS:
                skip_until_next_h3 = True
                continue
            if skip_until_next_h3 and node.level is not None and node.level <= 3:
                skip_until_next_h3 = False

        if skip_until_next_h3:
            continue

        # Drop ad buttons
        if (node.type == NodeType.INTERACTIVE
                and node.role == "button"
                and (node.name or "").strip().lower() in _DROP_BUTTONS):
            continue

        result.append(node)

    # --- Phase 3: truncate at footer ---
    final: list[DomNode] = []
    for node in result:
        if node.type == NodeType.HEADING:
            name_lower = (node.name or "").strip().lower()
            if name_lower in _FOOTER_HEADINGS:
                break
        final.append(node)

    return final
