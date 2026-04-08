"""File download detection and handling for browser navigation responses.

Detects when a navigation or interaction results in a file (PDF, image,
archive, etc.) rather than an HTML page, and provides utilities to save
the file and report it to the agent.
"""

from __future__ import annotations

import logging
import mimetypes
import uuid
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Content types that the DOM walker can meaningfully process, plus web
# resource types (JS, CSS, fonts, etc.) that should never be treated as
# file downloads even if they appear as a main-frame response.
_PAGE_CONTENT_TYPES = frozenset({
    "text/html",
    "application/xhtml+xml",
    "application/json",
    "text/plain",
    "text/xml",
    "application/xml",
    # Web resources — not downloadable files
    "application/javascript",
    "text/javascript",
    "text/css",
    "application/wasm",
    "text/csv",
    "application/manifest+json",
    "application/ld+json",
    "image/svg+xml",
})


class DownloadInfo(BaseModel):
    """Metadata about a downloaded file.

    Attributes:
        path: Absolute path to the saved file.
        content_type: MIME type of the downloaded file.
        size_bytes: File size in bytes.
        filename: The filename (basename) of the saved file.
    """

    path: str
    content_type: str
    size_bytes: int
    filename: str


def is_file_content_type(content_type: str) -> bool:
    """Return True if the content-type indicates a downloadable file.

    HTML, JSON, plain text, and XML are considered "page" content that the
    DOM walker can handle.  Everything else (PDF, images, archives, etc.)
    is treated as a file.

    Args:
        content_type: The raw Content-Type header value (may include charset).

    Returns:
        True if the content represents a file rather than a web page.
    """
    base = content_type.split(";")[0].strip().lower()
    if not base:
        return False
    return base not in _PAGE_CONTENT_TYPES


async def save_response_as_file(
    response: object,
    downloads_dir: str | Path,
) -> DownloadInfo:
    """Download the response body and save it to disk.

    Args:
        response: Playwright Response object with ``.body()`` and ``.url``.
        downloads_dir: Directory to save the file into.

    Returns:
        DownloadInfo with the saved file's metadata.
    """
    dl_path = Path(downloads_dir)
    dl_path.mkdir(parents=True, exist_ok=True)

    # Derive filename from URL or generate one
    url: str = getattr(response, "url", "")
    url_path = url.split("?")[0].split("#")[0]
    basename = url_path.rstrip("/").rsplit("/", 1)[-1] if "/" in url_path else ""

    if not basename or len(basename) > 200:
        # Guess extension from content-type
        ct = _get_content_type(response)
        ext = mimetypes.guess_extension(ct.split(";")[0].strip()) or ""
        basename = f"{uuid.uuid4().hex[:12]}{ext}"

    dest = dl_path / basename
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        basename = f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"
        dest = dl_path / basename

    body: bytes = await response.body()

    # Chromium's PDF viewer replaces the response body with an HTML wrapper.
    # Detect this and re-fetch the raw file via the API request context.
    ct = _get_content_type(response)
    if _is_viewer_html(body, ct):
        refetched = await _refetch_raw_bytes(response, url)
        if refetched:
            body = refetched

    dest.write_bytes(body)

    size = len(body)

    logger.info(
        "Saved file download: %s (%s, %d bytes)", dest, ct, size,
    )

    return DownloadInfo(
        path=str(dest),
        content_type=ct,
        size_bytes=size,
        filename=basename,
    )


def _is_viewer_html(body: bytes, expected_ct: str) -> bool:
    """Return True if the body is a Chromium viewer HTML wrapper.

    Chromium replaces PDF/media responses with a small HTML page containing
    an ``<embed>`` tag. We detect this by checking for HTML markers in a
    body that should be a non-HTML content type.
    """
    if not body or len(body) > 2048:
        # Real files are usually larger; viewer HTML is tiny (~350 bytes)
        return False
    base_ct = expected_ct.split(";")[0].strip().lower()
    if base_ct in ("text/html", "application/xhtml+xml"):
        return False
    try:
        text = body.decode("utf-8", errors="ignore").lower()
    except Exception:
        return False
    return "<html>" in text and "<embed" in text


async def _refetch_raw_bytes(response: object, url: str) -> bytes:
    """Re-fetch a URL via the Playwright API request context to get raw bytes.

    The API request context bypasses the browser renderer, so it returns
    the actual file bytes instead of the Chromium viewer HTML.
    """
    try:
        frame = getattr(response, "frame", None)
        page = getattr(frame, "page", None) if frame else None
        if page is not None:
            api_response = await page.context.request.get(url)
            raw = await api_response.body()
            await api_response.dispose()
            logger.info(
                "Re-fetched raw file bytes via API context: %d bytes", len(raw),
            )
            return raw
    except Exception:
        logger.exception("Failed to re-fetch raw bytes for %s", url)
    # Caller should fall back to the body it already has
    return b""


def build_download_info_from_path(
    path: str | Path,
    content_type: str | None = None,
) -> DownloadInfo:
    """Build a DownloadInfo from an already-saved file on disk.

    Used for Playwright download events where the file is saved automatically.

    Args:
        path: Absolute path to the saved file.
        content_type: MIME type override. Guessed from filename if None.

    Returns:
        DownloadInfo with the file's metadata.
    """
    p = Path(path)
    if content_type is None:
        content_type, _ = mimetypes.guess_type(p.name)
        content_type = content_type or "application/octet-stream"

    return DownloadInfo(
        path=str(p),
        content_type=content_type,
        size_bytes=p.stat().st_size if p.exists() else 0,
        filename=p.name,
    )


def format_download_message(info: DownloadInfo) -> str:
    """Format a human-readable message describing a downloaded file.

    Args:
        info: The download metadata.

    Returns:
        A string suitable for use as PageView.content.
    """
    size_str = _format_size(info.size_bytes)
    return (
        f"Downloaded file: {info.path}\n"
        f"Type: {info.content_type}\n"
        f"Size: {size_str}\n"
        f"\nUse run_bash_cmd to inspect or process this file."
    )


def _get_content_type(response: object) -> str:
    """Extract content-type from a Playwright Response."""
    headers = getattr(response, "headers", {})
    if isinstance(headers, dict):
        return headers.get("content-type", "application/octet-stream")
    return "application/octet-stream"


def _format_size(size_bytes: int) -> str:
    """Format byte count as human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


__all__ = [
    "DownloadInfo",
    "build_download_info_from_path",
    "format_download_message",
    "is_file_content_type",
    "save_response_as_file",
]
