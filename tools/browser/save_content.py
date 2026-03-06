"""Browser tool for saving page content to the virtual computer."""

from __future__ import annotations

import logging
from pathlib import Path

import html2text
from pydantic import BaseModel

from config import load_config
from tools.browser.core import get_active_view
from tools.browser.core.exceptions import BrowserToolError

logger = logging.getLogger(__name__)

# Reusable converter — configured once, thread-safe for reads.
_converter = html2text.HTML2Text()
_converter.ignore_images = True
_converter.ignore_emphasis = False
_converter.body_width = 0  # no line wrapping
_converter.protect_links = True
_converter.unicode_snob = True


class SaveContentResult(BaseModel):
    """Result of saving page content to the virtual computer.

    Attributes:
        filename: The filename that was saved.
        container_path: Absolute path accessible from inside the container.
        size_bytes: File size in bytes.
    """

    filename: str
    container_path: str
    size_bytes: int


async def save_page_content(filename: str) -> SaveContentResult:
    """Save the current page as markdown to /home/computron/<filename>.

    Use when ``read_page()`` output is truncated and you need the full page
    for processing with ``run_bash_cmd()`` (e.g. grep, cat).

    Args:
        filename: Plain filename without directories (e.g. ``"page.md"``).

    Returns:
        SaveContentResult with filename and container path.
    """
    _, view = await get_active_view("save_page_content")

    # Reject paths with directory separators to keep files in the home dir
    if "/" in filename or "\\" in filename:
        msg = "filename must be a plain name without directory separators."
        raise BrowserToolError(msg, tool="save_page_content")

    config = load_config()
    home_dir = Path(config.virtual_computer.home_dir)
    container_working_dir = config.virtual_computer.container_working_dir.rstrip("/")

    host_path = home_dir / filename
    container_path = f"{container_working_dir}/{filename}"

    logger.info("Saving page content from %s to %s", view.url, host_path)

    try:
        raw_html = await view.frame.content()
        content = _converter.handle(raw_html)
        home_dir.mkdir(parents=True, exist_ok=True)
        host_path.write_text(content, encoding="utf-8")
        size = host_path.stat().st_size

        logger.info("Saved %d bytes to %s", size, host_path)
        return SaveContentResult(
            filename=filename,
            container_path=container_path,
            size_bytes=size,
        )
    except BrowserToolError:
        raise
    except Exception as exc:
        logger.exception("Failed to save page content to %s", host_path)
        raise BrowserToolError(str(exc), tool="save_page_content") from exc


__all__ = ["SaveContentResult", "save_page_content"]
