"""Browser tool: open a URL and return a lightweight page snapshot.

Implementation delegates snapshot extraction to shared internal helper
``_build_page_snapshot`` located in ``tools.browser.core.snapshot`` so
other tools can re-use consistent snapshot semantics.
"""

from __future__ import annotations

import logging

from tools.browser.core import get_browser
from tools.browser.core.snapshot import PageSnapshot, _build_page_snapshot
from tools.browser.exceptions import BrowserToolError

logger = logging.getLogger(__name__)


# NOTE: Link/Form/PageSnapshot now live in tools.browser.core.snapshot.
# If external callers previously imported them from this module they should
# update imports. We intentionally do not re-export to keep surface minimal.


async def open_url(url: str) -> PageSnapshot:  # backward-compatible function name
    """Open a URL in the shared browser and return a compact snapshot.

    Args:
        url: The URL to open (http/https).

    Returns:
        PageSnapshot: Pydantic model with title, url, snippet, links, forms, status_code.

    Raises:
        BrowserToolError: If navigation or extraction fails.
    """
    try:
        browser = await get_browser()
        page = await browser.new_page()
        response = await page.goto(url, wait_until="domcontentloaded")
        return await _build_page_snapshot(page, response)
    except Exception as exc:  # pragma: no cover - wrap into tool error
        logger.exception("Failed to open URL %s", url)
        raise BrowserToolError(str(exc), tool="open_url") from exc
