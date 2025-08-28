"""Read operations: read range, head, tail.

Simple, UTF-8 only helpers designed for LLM ergonomics.
"""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING

from ._fs_internal import is_binary_file
from ._path_utils import resolve_under_home
from .models import ReadTextResult

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable
    from pathlib import Path


def _read_text_iter(path: Path) -> Iterable[str]:
    """Yield lines from a UTF-8 text file with replacement on errors."""
    with path.open("r", encoding="utf-8", errors="replace") as f:
        yield from f


def read_file(path: str, start: int | None = None, end: int | None = None) -> ReadTextResult:
    """Read a UTF-8 text file fully or by inclusive 1-based line range.

    Args:
        path: Relative or absolute path under the virtual computer home.
        start: Optional inclusive start line (1-based). If None, begins at 1.
        end: Optional inclusive end line (1-based). If None, reads to EOF.

    Returns:
        ReadTextResult: Success flag, normalized relative ``file_path``,
        content string (or None on failure), and optional range info.

    Raises:
        None: errors are returned in the result and logged.
    """
    try:
        abs_path, _home, rel = resolve_under_home(path)
        if not abs_path.exists() or not abs_path.is_file():
            return ReadTextResult(
                success=False,
                file_path=rel,
                content=None,
                error="file not found",
            )
        if is_binary_file(abs_path):
            return ReadTextResult(
                success=False,
                file_path=rel,
                content=None,
                error="binary file not supported",
            )

        # Fast path: no range requested
        if start is None and end is None:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
            total_lines = content.count("\n") + (
                0 if (content == "" or content.endswith("\n")) else 1
            )
            return ReadTextResult(
                success=True,
                file_path=rel,
                content=content,
                total_lines=total_lines,
            )

        # Normalize range
        s = 1 if start is None else max(1, start)
        e = end if end is not None and end >= s else None
        total = 0
        out_buf = io.StringIO()
        for idx, line in enumerate(_read_text_iter(abs_path), start=1):
            total += 1
            if idx < s:
                continue
            if e is not None and idx > e:
                break
            out_buf.write(line)
        content = out_buf.getvalue()
        return ReadTextResult(
            success=True,
            file_path=rel,
            content=content,
            start=s,
            end=e,
            total_lines=total,
        )
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to read file %s", path)
        return ReadTextResult(success=False, file_path=path, content=None, error="read failed")


def head(path: str, n: int = 200) -> ReadTextResult:
    """Read the first n lines of a UTF-8 text file.

    Args:
        path: File path (relative or absolute under home).
        n: Number of lines to return. Defaults to 200.

    Returns:
        ReadTextResult: Content of the first n lines with range metadata.
    """
    return read_file(path, start=1, end=max(1, n))


def tail(path: str, n: int = 200) -> ReadTextResult:
    """Read the last n lines of a UTF-8 text file using a rolling buffer.

    Args:
        path: File path (relative or absolute under home).
        n: Number of lines to return. Defaults to 200.

    Returns:
        ReadTextResult: Content of the last n lines with range metadata when known.
    """
    try:
        abs_path, _home, rel = resolve_under_home(path)
        if not abs_path.exists() or not abs_path.is_file():
            return ReadTextResult(
                success=False,
                file_path=rel,
                content=None,
                error="file not found",
            )
        if is_binary_file(abs_path):
            return ReadTextResult(
                success=False,
                file_path=rel,
                content=None,
                error="binary file not supported",
            )
        # Rolling buffer of last n lines
        buf: list[str] = []
        total = 0
        for line in _read_text_iter(abs_path):
            total += 1
            buf.append(line)
            if len(buf) > max(1, n):
                buf.pop(0)
        effective_n = max(1, n)
        content = "".join(buf[-effective_n:])
        start_line = max(1, total - effective_n + 1) if total > 0 else 1
        end_line = total if total > 0 else 1
        return ReadTextResult(
            success=True,
            file_path=rel,
            content=content,
            start=start_line,
            end=end_line,
            total_lines=total,
        )
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to tail file %s", path)
        return ReadTextResult(success=False, file_path=path, content=None, error="tail failed")
