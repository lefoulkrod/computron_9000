"""Edit operations for files: replace literal strings and insert text by anchor.

UTF-8 only, atomic writes.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Final

from tools._truncation import truncate_args

from ._fs_internal import is_binary_file, write_text_lines
from .models import InsertTextResult, ReplaceInFileResult

logger = logging.getLogger(__name__)


_WHERE_VALUES: Final[set[str]] = {"after", "before", "replace"}
_OCCURRENCE_VALUES: Final[set[str]] = {"first", "all"}


@truncate_args(replacement=200)
def replace_in_file(
    path: str,
    pattern: str,
    replacement: str,
) -> ReplaceInFileResult:
    """Replace all occurrences of a literal string in a text file.

    Args:
        path: File path.
        pattern: Literal string to find. All occurrences are replaced.
        replacement: Replacement text.

    Returns:
        ReplaceInFileResult: Success flag, ``file_path``, and count of replacements.
    """
    try:
        abs_path = Path(path)
        if not abs_path.exists() or not abs_path.is_file():
            return ReplaceInFileResult(
                success=False,
                file_path=path,
                replacements=0,
                error="file not found",
            )
        if is_binary_file(abs_path):
            return ReplaceInFileResult(
                success=False,
                file_path=path,
                replacements=0,
                error="binary file not supported",
            )

        text = abs_path.read_text(encoding="utf-8", errors="replace")
        count = text.count(pattern)
        new_text = text.replace(pattern, replacement)

        if count > 0:
            write_text_lines(abs_path, new_text.splitlines(keepends=True))

        return ReplaceInFileResult(
            success=True,
            file_path=path,
            replacements=count,
        )
    except OSError:  # pragma: no cover - defensive
        logger.exception("replace_in_file failed for %s", path)
        return ReplaceInFileResult(
            success=False,
            file_path=path,
            replacements=0,
            error="replace failed",
        )


@truncate_args(text=200)
def insert_text(
    path: str,
    anchor: str,
    text: str,
    *,
    where: str = "after",
    occurrences: str = "first",
) -> InsertTextResult:
    """Insert text relative to a literal anchor string within a file.

    Args:
        path: File path.
        anchor: Literal string to locate the insertion point.
        text: Text to insert or replace with.
        where: One of ``{"after","before","replace"}``. Default "after".
        occurrences: One of ``{"first","all"}``. Default "first".

    Returns:
        InsertTextResult: Success, relative path, and count of occurrences changed.
    """
    if where not in _WHERE_VALUES:
        return InsertTextResult(
            success=False,
            file_path=path,
            occurrences=0,
            where=where,
            error="invalid where",
        )
    if occurrences not in _OCCURRENCE_VALUES:
        return InsertTextResult(
            success=False,
            file_path=path,
            occurrences=0,
            where=where,
            error="invalid occurrences",
        )

    try:
        abs_path = Path(path)
        if not abs_path.exists() or not abs_path.is_file():
            return InsertTextResult(
                success=False,
                file_path=path,
                occurrences=0,
                where=where,
                error="file not found",
            )
        if is_binary_file(abs_path):
            return InsertTextResult(
                success=False,
                file_path=path,
                occurrences=0,
                where=where,
                error="binary file not supported",
            )

        text_src = abs_path.read_text(encoding="utf-8", errors="replace")
        patt = re.compile(re.escape(anchor))

        def repl(m: re.Match[str]) -> str:
            if where == "after":
                return m.group(0) + text
            if where == "before":
                return text + m.group(0)
            return text

        if occurrences == "first":
            new_text, count = patt.subn(repl, text_src, count=1)
        else:
            new_text, count = patt.subn(repl, text_src)

        if count == 0:
            return InsertTextResult(
                success=False,
                file_path=path,
                occurrences=0,
                where=where,
                error="anchor not found",
            )

        write_text_lines(abs_path, new_text.splitlines(keepends=True))
        return InsertTextResult(
            success=True,
            file_path=path,
            occurrences=count,
            where=where,
        )
    except OSError:  # pragma: no cover - defensive
        logger.exception("insert_text failed for %s", path)
        return InsertTextResult(
            success=False,
            file_path=path,
            occurrences=0,
            where=where,
            error="insert failed",
        )
