"""Browser tool for saving page content to the virtual computer."""

from __future__ import annotations

import logging
from pathlib import Path

from config import load_config
from tools.browser.core import get_active_view
from tools.browser.core._formatting import format_save_result
from tools.browser.core._html import html_to_markdown
from tools.browser.core.exceptions import BrowserToolError

logger = logging.getLogger(__name__)


async def save_page_content(filename: str) -> str:
    """Save the current page as markdown to /home/computron/<filename>.

    Use when ``read_page()`` output is truncated and you need the full page
    for processing with ``run_bash_cmd()`` (e.g. grep, cat).

    Args:
        filename: Plain filename without directories (e.g. ``"page.md"``).

    Returns:
        Formatted string with filename, container path, and size.
    """
    _, view = await get_active_view("save_page_content")

    # Reject paths with directory separators to keep files in the home dir
    if "/" in filename or "\\" in filename:
        msg = "filename must be a plain name without directory separators."
        raise BrowserToolError(msg, tool="save_page_content")

    config = load_config()
    home_dir = Path(config.virtual_computer.home_dir)

    host_path = home_dir / filename
    file_path = str(host_path)

    logger.info("Saving page content from %s to %s", view.url, host_path)

    try:
        raw_html = await view.frame.content()
        content = html_to_markdown(raw_html)
        home_dir.mkdir(parents=True, exist_ok=True)
        host_path.write_text(content, encoding="utf-8")
        size = host_path.stat().st_size

        logger.info("Saved %d bytes to %s", size, host_path)
        return format_save_result(
            filename=filename,
            container_path=file_path,
            size_bytes=size,
        )
    except BrowserToolError:
        raise
    except Exception as exc:
        logger.exception("Failed to save page content to %s", host_path)
        raise BrowserToolError(str(exc), tool="save_page_content") from exc


__all__ = ["save_page_content"]
