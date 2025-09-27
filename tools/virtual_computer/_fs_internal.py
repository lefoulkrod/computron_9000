"""Low-level file IO helpers used by higher-level ops and patching modules."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


# --- Generic helpers -----------------------------------------------------------------


def read_text_lines(path: Path) -> list[str]:  # pragma: no cover - simple
    """Read a text file into a list of lines.

    Args:
        path: Absolute filesystem path to read.

    Returns:
        list[str]: Lines read using UTF-8 with replacement for decode errors.
    """
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return f.readlines()


def write_text_lines(path: Path, lines: list[str]) -> None:  # pragma: no cover - simple
    """Atomically write a list of lines to a file.

    Writes to a temporary file and then replaces the target path.

    Args:
        path: Absolute filesystem path to write.
        lines: List of text lines (should include trailing newlines where
            desired).
    """
    tmp = path.with_suffix(path.suffix + ".patchtmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.writelines(lines)
    tmp.replace(path)


def is_binary_file(file_path: Path) -> bool:
    """Heuristically determine if a file is binary.

    Inspects up to the first 1024 bytes to check for NUL bytes.

    Args:
        file_path: Absolute filesystem path to examine.

    Returns:
        bool: True if the file appears to be binary; False otherwise.
    """
    try:
        with file_path.open("rb") as f:
            return b"\0" in f.read(1024)
    except OSError as exc:  # pragma: no cover - defensive
        logger.warning("Could not determine if file is binary: %s", exc)
        return False
