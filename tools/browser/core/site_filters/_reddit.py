"""Reddit site filter — strips navigation chrome, sidebar, and per-post noise."""

from __future__ import annotations

from tools.browser.core._dom_nodes import DomNode, NodeType

# Buttons that appear on every post and waste tokens
_DROP_BUTTONS = frozenset({
    "open user actions",
    "share",
    "upvote",
    "downvote",
    "join",
    "expand user menu",
    "collapse navigation",
    "start a community",
    "create custom feed",
    "manage communities",
    # Video player controls
    "toggle playback",
    "media time",
    "toggle captions",
    "settings",
    "toggle fullscreen",
    "toggle volume",
    # Image carousel controls
    "previous page",
    "next page",
})

# Buttons matching these prefixes are dropped
_DROP_BUTTON_PREFIXES = (
    "page ",        # "Page 1 (Current page)", "Page 2", etc.
    "item ",        # "Item 1 of 3"
    "give award",   # "Give award", "Give award, 2 awards given"
)

# Links that are navigation chrome, not content
_DROP_LINKS = frozenset({
    "skip to main content",
    "skip to navigation",
    "skip to right sidebar",
    "advertise on reddit",
    "promoted",
    # Footer
    "reddit rules",
    "privacy policy",
    "user agreement",
    "your privacy choices",
    "accessibility",
})

# Links matching these prefixes are dropped
_DROP_LINK_PREFIXES = (
    "reddit, inc.",
    "best of reddit",
)

# Left sidebar section headings — everything from these onward in the sidebar
# is navigation noise
_SIDEBAR_BUTTONS = frozenset({
    "games on reddit",
    "custom feeds",
    "communities",
    "resources",
    "recent",
})

# Sidebar game/nav links
_SIDEBAR_LINKS = frozenset({
    "featured game",
    "petpost",
    "readit game",
    "bubble shooter pro",
    "discover more",
    "about reddit",
    "advertise",
    "developer platform",
    "reddit pro",
    "help",
    "blog",
    "careers",
    "press",
    "communities",
    "best of reddit",
})

# Text fragments indicating ad/promoted content
_AD_TEXT = (
    "promoted",
    "advertisement",
    "sponsored",
)


def _name_lower(node: DomNode) -> str:
    return (node.name or "").strip().lower()


def _text_lower(node: DomNode) -> str:
    return (node.text or "").strip().lower()


def _is_noise(node: DomNode) -> bool:
    """Return True for Reddit-specific noise nodes."""
    name = _name_lower(node)
    text = _text_lower(node)

    if node.type == NodeType.INTERACTIVE:
        if node.role == "button":
            # Exact match drops
            if name in _DROP_BUTTONS:
                return True
            # Prefix match drops (carousel, pagination)
            for prefix in _DROP_BUTTON_PREFIXES:
                if name.startswith(prefix):
                    return True
            # Sidebar section toggles
            if name in _SIDEBAR_BUTTONS:
                return True

        if node.role == "link":
            if name in _DROP_LINKS:
                return True
            if name in _SIDEBAR_LINKS:
                return True
            for prefix in _DROP_LINK_PREFIXES:
                if name.startswith(prefix):
                    return True

    # Ad text nodes
    if node.type == NodeType.TEXT:
        for frag in _AD_TEXT:
            if frag in text:
                return True

    return False


def _is_ad_post_start(node: DomNode) -> bool:
    """Check if a link node looks like an ad/promoted post title."""
    name = _name_lower(node)
    return name.startswith("advertisement:")


def filter_reddit(nodes: list[DomNode]) -> list[DomNode]:
    """Strip Reddit navigation chrome, sidebar, and per-post noise.

    Phase 1: Keep search bar, drop skip links and top-nav buttons before
    first content heading.
    Phase 2: Remove per-post noise (vote buttons, share, awards, video
    controls, carousel pagination).
    Phase 3: Drop promoted/ad posts entirely.
    Phase 4: Truncate at footer / sidebar navigation sections.
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

        # Keep search textbox and its dropdown items (menuitems/options)
        if node.type == NodeType.INTERACTIVE:
            name = _name_lower(node)
            if (node.role in {"textbox", "searchbox"}
                    and ("find anything" in name or "search" in name)):
                after_nav.append(node)
                i += 1
                continue
            if node.role in {"menuitem", "option"}:
                after_nav.append(node)
                i += 1
                continue
            # "Clear search" button
            if node.role == "button" and name == "clear search":
                after_nav.append(node)
                i += 1
                continue

        # h1, h2, or sort/view buttons mark start of content
        if node.type == NodeType.HEADING:
            found_content = True
            after_nav.append(node)
            i += 1
            continue

        # Sort/view controls are useful
        if (node.type == NodeType.INTERACTIVE
                and node.role == "button"
                and (_name_lower(node).startswith("sort by")
                     or _name_lower(node).startswith("view:"))):
            after_nav.append(node)
            i += 1
            continue

        i += 1

    if not found_content:
        after_nav = nodes

    # --- Phase 2: remove per-node noise ---
    cleaned = [n for n in after_nav if not _is_noise(n)]

    # --- Phase 3: drop promoted/ad posts ---
    # An ad post starts with a link whose name begins with "advertisement:"
    # and runs until the next non-ad post link or heading
    result: list[DomNode] = []
    skip_ad = False
    for node in cleaned:
        if node.type == NodeType.INTERACTIVE and node.role == "link":
            if _is_ad_post_start(node):
                skip_ad = True
                continue
            # A real post link (not a subreddit or user link) ends the ad skip
            name = _name_lower(node)
            if skip_ad and not name.startswith("r/") and not name.startswith("u/"):
                skip_ad = False

        if node.type == NodeType.HEADING:
            skip_ad = False

        if skip_ad:
            continue

        result.append(node)

    # --- Phase 4: truncate at footer / sidebar nav ---
    # Look for footer markers: "Reddit Rules" link, or the sidebar nav
    # links that follow the main content (Home/Popular/News/Explore sequence).
    final: list[DomNode] = []
    for idx, node in enumerate(result):
        name = _name_lower(node)
        if node.type == NodeType.INTERACTIVE and node.role == "link":
            if name == "reddit rules":
                break
            # Detect sidebar nav: "Home" link followed by "Popular"
            if name == "home" and idx + 1 < len(result):
                nxt = result[idx + 1]
                if (_name_lower(nxt) == "popular"
                        and nxt.type == NodeType.INTERACTIVE
                        and nxt.role == "link"):
                    break
        final.append(node)

    return final
