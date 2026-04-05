"""Write incoming file attachments to the uploads directory."""

from __future__ import annotations

import base64
import logging
import mimetypes
import uuid
from pathlib import Path

from config import load_config

logger = logging.getLogger(__name__)


def receive_attachment(
    base64_encoded: str,
    content_type: str,
    filename: str | None = None,
) -> str:
    """Decode a base64-encoded file and write it to the uploads directory.

    Args:
        base64_encoded: Base64-encoded file content.
        content_type: MIME type of the file.
        filename: Original filename. A UUID-based name is generated if absent.

    Returns:
        The absolute path to the saved file.
    """
    cfg = load_config()
    home_dir = Path(cfg.virtual_computer.home_dir)

    uploads_dir = home_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        ext = mimetypes.guess_extension(content_type) or ""
        filename = f"{uuid.uuid4().hex}{ext}"

    dest = uploads_dir / filename
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        filename = f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"
        dest = uploads_dir / filename

    raw = base64.b64decode(base64_encoded)
    dest.write_bytes(raw)
    logger.info("Wrote attachment to %s (%d bytes, %s)", dest, len(raw), content_type)

    return str(dest)
