"""Site-specific node filters for the DOM pipeline.

Pluggable filters that prune noise from known sites, letting the LLM
focus on actionable content.  Each filter receives and returns a flat
``list[DomNode]`` — the same interface used by ``_filter_viewport``
and ``_filter_scope``.

To add a new site filter, create a module in this package with a public
``filter_<site>(nodes)`` function, then register it in ``_SITE_FILTERS``.
"""

from __future__ import annotations

from collections.abc import Callable

from tools.browser.core._dom_nodes import DomNode
from tools.browser.core.site_filters._amazon import filter_amazon
from tools.browser.core.site_filters._ebay import filter_ebay
from tools.browser.core.site_filters._reddit import filter_reddit

_SITE_FILTERS: dict[str, Callable[[list[DomNode]], list[DomNode]]] = {
    "amazon.com": filter_amazon,
    "ebay.com": filter_ebay,
    "reddit.com": filter_reddit,
}


def filter_for_site(url: str, nodes: list[DomNode]) -> list[DomNode]:
    """Apply a site-specific filter if one matches the URL.

    Args:
        url: The current page URL.
        nodes: Flat list of DOM nodes from earlier pipeline stages.

    Returns:
        Filtered node list (unchanged if no site filter matches).
    """
    for domain, fn in _SITE_FILTERS.items():
        if domain in url:
            return fn(nodes)
    return nodes


__all__ = ["filter_for_site"]
