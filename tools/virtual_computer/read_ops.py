"""Read operations: read range, head, tail.

Simple, UTF-8 only helpers designed for LLM ergonomics.
Content is returned with embedded line numbers (like ``cat -n``) so the model
sees line references in context.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ._fs_internal import is_binary_file
from .models import ReadTextResult

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable


def _read_text_iter(path: Path) -> Iterable[str]:
    """Yield lines from a UTF-8 text file with replacement on errors."""
    with path.open("r", encoding="utf-8", errors="replace") as f:
        yield from f


_MAX_LINES_DEFAULT: int = 2000


def _numbered_line(lineno: int, text: str) -> str:
    """Format a line with its number, like ``cat -n``."""
    return f"{lineno:6d}\t{text}"


def read_file(path: str, start: int | None = None, end: int | None = None) -> ReadTextResult:
    """Read a UTF-8 text file fully or by line range.

    Content is returned with embedded line numbers (``cat -n`` style).
    Files over 2000 lines are automatically truncated when no range is given.
    Use ``start``/``end`` or ``grep`` to read specific sections of large files.

    Args:
        path: File path (relative or absolute).
        start: First line to read (1-based, inclusive). Omit to start at 1.
        end: Last line to read (1-based, inclusive). Omit to read to EOF.

    Returns:
        ReadTextResult: ``content`` with line numbers, ``total_lines``, and optional range info.
    """
    try:
        abs_path = Path(path)
        if not abs_path.exists() or not abs_path.is_file():
            return ReadTextResult(
                success=False,
                file_path=path,
                content=None,
                error="file not found",
            )
        if is_binary_file(abs_path):
            return ReadTextResult(
                success=False,
                file_path=path,
                content=None,
                error="binary file not supported",
            )

        # No range requested — read full but cap at _MAX_LINES_DEFAULT
        if start is None and end is None:
            lines: list[str] = []
            total_lines = 0
            for line in _read_text_iter(abs_path):
                total_lines += 1
                if total_lines <= _MAX_LINES_DEFAULT:
                    lines.append(_numbered_line(total_lines, line))

            content = "".join(lines)
            truncated = total_lines > _MAX_LINES_DEFAULT

            return ReadTextResult(
                success=True,
                file_path=path,
                content=content,
                start=1 if truncated else None,
                end=_MAX_LINES_DEFAULT if truncated else None,
                total_lines=total_lines,
                truncated=truncated,
            )

        # Explicit range requested
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
            out_buf.write(_numbered_line(idx, line))
        content = out_buf.getvalue()
        return ReadTextResult(
            success=True,
            file_path=path,
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
        path: File path (relative or absolute).
        n: Number of lines to return. Defaults to 200.

    Returns:
        ReadTextResult: Content of the first n lines with range metadata.
    """
    return read_file(path, start=1, end=max(1, n))


def tail(path: str, n: int = 200) -> ReadTextResult:
    """Read the last n lines of a UTF-8 text file.

    Args:
        path: File path (relative or absolute).
        n: Number of lines to return. Defaults to 200.

    Returns:
        ReadTextResult: Content of the last n lines with range metadata.
    """
    try:
        abs_path = Path(path)
        if not abs_path.exists() or not abs_path.is_file():
            return ReadTextResult(
                success=False,
                file_path=path,
                content=None,
                error="file not found",
            )
        if is_binary_file(abs_path):
            return ReadTextResult(
                success=False,
                file_path=path,
                content=None,
                error="binary file not supported",
            )
        # Rolling buffer of last n lines (keep raw + line number)
        buf: list[tuple[int, str]] = []
        total = 0
        for line in _read_text_iter(abs_path):
            total += 1
            buf.append((total, line))
            if len(buf) > max(1, n):
                buf.pop(0)
        effective_n = max(1, n)
        tail_items = buf[-effective_n:]
        content = "".join(_numbered_line(lineno, text) for lineno, text in tail_items)
        start_line = max(1, total - effective_n + 1) if total > 0 else 1
        end_line = total if total > 0 else 1
        return ReadTextResult(
            success=True,
            file_path=path,
            content=content,
            start=start_line,
            end=end_line,
            total_lines=total,
        )
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to tail file %s", path)
        return ReadTextResult(success=False, file_path=path, content=None, error="tail failed")
