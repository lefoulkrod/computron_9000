"""Low-level file IO helpers used by higher-level ops and patching modules."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


# --- Generic helpers -----------------------------------------------------------------


def read_text_lines(path: Path) -> list[str]:  # pragma: no cover - simple
    """Return file lines (UTF-8, lenient)."""
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return f.readlines()


def write_text_lines(path: Path, lines: list[str]) -> None:  # pragma: no cover - simple
    """Atomically write lines to a path."""
    tmp = path.with_suffix(path.suffix + ".patchtmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.writelines(lines)
    tmp.replace(path)


def is_binary_file(file_path: Path) -> bool:
    """Return True if file appears binary, else False."""
    try:
        with file_path.open("rb") as f:
            return b"\0" in f.read(1024)
    except OSError as exc:  # pragma: no cover - defensive
        logger.warning("Could not determine if file is binary: %s", exc)
        return False
