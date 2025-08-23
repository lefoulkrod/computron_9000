"""Edit operations for files: replace patterns and insert text by anchor.

UTF-8 only, atomic writes, and safe path resolution under the workspace.
"""

from __future__ import annotations

import logging
import re
from typing import Final

from .models import InsertTextResult, ReplaceInFileResult
from .ops_internal import is_binary_file, write_text_lines
from .path_utils import resolve_under_home

logger = logging.getLogger(__name__)


_WHERE_VALUES: Final[set[str]] = {"after", "before", "replace"}
_OCCURRENCE_VALUES: Final[set[str]] = {"first", "all"}


def replace_in_file(
    path: str,
    pattern: str,
    replacement: str,
    *,
    regex: bool = True,
    preview_only: bool = False,
) -> ReplaceInFileResult:
    """Replace occurrences of a pattern in a text file.

    Args:
        path: File path under the virtual computer home.
        pattern: Regex or literal pattern to replace.
        replacement: Replacement text.
        regex: If True (default), treat ``pattern`` as regex; otherwise literal.
        preview_only: If True, do not write changes; only count replacements.

    Returns:
        ReplaceInFileResult: Success flag, relative ``file_path``, and count of replacements.
    """
    try:
        abs_path, _home, rel = resolve_under_home(path)
        if not abs_path.exists() or not abs_path.is_file():
            return ReplaceInFileResult(
                success=False,
                file_path=rel,
                replacements=0,
                preview=preview_only,
                error="file not found",
            )
        if is_binary_file(abs_path):
            return ReplaceInFileResult(
                success=False,
                file_path=rel,
                replacements=0,
                preview=preview_only,
                error="binary file not supported",
            )

        text = abs_path.read_text(encoding="utf-8", errors="replace")
        if regex:
            patt = re.compile(pattern)
            new_text, count = patt.subn(replacement, text)
        else:
            # Literal replace
            count = text.count(pattern)
            new_text = text.replace(pattern, replacement)

        if count > 0 and not preview_only:
            write_text_lines(abs_path, new_text.splitlines(keepends=True))

        return ReplaceInFileResult(
            success=True,
            file_path=rel,
            replacements=count,
            preview=preview_only,
        )
    except OSError:  # pragma: no cover - defensive
        logger.exception("replace_in_file failed for %s", path)
        return ReplaceInFileResult(
            success=False,
            file_path=path,
            replacements=0,
            preview=preview_only,
            error="replace failed",
        )


def insert_text(
    path: str,
    anchor: str,
    text: str,
    *,
    where: str = "after",
    occurrences: str = "first",
    regex: bool = True,
) -> InsertTextResult:
    """Insert text relative to an anchor pattern within a file.

    Args:
        path: File path under the virtual computer home.
        anchor: Regex or literal anchor to match.
        text: Text to insert or replace with.
        where: One of ``{"after","before","replace"}``. Default "after".
        occurrences: One of ``{"first","all"}``. Default "first".
        regex: If True (default), treat ``anchor`` as regex; otherwise literal.

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
        abs_path, _home, rel = resolve_under_home(path)
        if not abs_path.exists() or not abs_path.is_file():
            return InsertTextResult(
                success=False,
                file_path=rel,
                occurrences=0,
                where=where,
                error="file not found",
            )
        if is_binary_file(abs_path):
            return InsertTextResult(
                success=False,
                file_path=rel,
                occurrences=0,
                where=where,
                error="binary file not supported",
            )

        text_src = abs_path.read_text(encoding="utf-8", errors="replace")
        patt = re.compile(anchor) if regex else re.compile(re.escape(anchor))

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
                file_path=rel,
                occurrences=0,
                where=where,
                error="anchor not found",
            )

        write_text_lines(abs_path, new_text.splitlines(keepends=True))
        return InsertTextResult(
            success=True,
            file_path=rel,
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
