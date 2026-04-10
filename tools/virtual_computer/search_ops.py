"""Search operations: grep across files in the current workspace.

Skips binary files; returns structured matches suitable for LLM consumption.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable

from ._fs_internal import is_binary_file
from .models import GrepMatch, GrepResult

logger = logging.getLogger(__name__)


def _iter_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_file():
            yield p


def _expand_globstar_zero_depth(pattern: str) -> set[str]:
    """Expand a pattern so that each "**/" can also be zero directories.

    Example: "src/**/*.js" -> {"src/**/*.js", "src/*.js"}
    Works for multiple occurrences by generating all combinations.
    """
    pat = pattern.replace("\\", "/")
    token = "**/"
    if token not in pat:
        return {pat}
    parts = pat.split(token)
    # Reconstruct with either token kept or removed at each junction
    variants: set[str] = set()
    n = len(parts) - 1
    # Each bit in mask: 1 means keep token, 0 means drop
    for mask in range(1 << n):
        s = parts[0]
        for i in range(n):
            s += (token if (mask & (1 << i)) else "") + parts[i + 1]
        variants.add(s)
    return variants


def _apply_globs(
    paths: Iterable[Path],
    root: Path,
    include: list[str] | None,
    exclude: list[str] | None,
) -> Iterable[Path]:
    """Filter paths by include/exclude patterns using Path.glob (globstar-on).

    We expand include and exclude patterns using ``root.glob`` which supports
    ``**`` for recursive matches. Only files are considered.
    """
    # Build sets of included/excluded file Paths for fast membership checks
    included: set[Path] | None = None
    excluded: set[Path] = set()

    if include:
        inc_set: set[Path] = set()
        for pat in include:
            for expanded in _expand_globstar_zero_depth(pat):
                for gp in root.glob(expanded):
                    if gp.is_file():
                        inc_set.add(gp)
                    elif gp.is_dir():
                        for fp in gp.rglob("*"):
                            if fp.is_file():
                                inc_set.add(fp)
        included = inc_set

    if exclude:
        for pat in exclude:
            for expanded in _expand_globstar_zero_depth(pat):
                for gp in root.glob(expanded):
                    if gp.is_file():
                        excluded.add(gp)
                    elif gp.is_dir():
                        for fp in gp.rglob("*"):
                            if fp.is_file():
                                excluded.add(fp)

    for p in paths:
        if included is not None and p not in included:
            continue
        if p in excluded:
            continue
        yield p


def grep(
    pattern: str,
    *,
    path: str = ".",
    include_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
    regex: bool = True,
    case_sensitive: bool = False,
    context: int = 2,
    max_results: int | None = 1000,
) -> GrepResult:
    """Search workspace files for a pattern.

    Args:
        pattern: Regex or literal pattern to search for.
        path: File or directory to search in. Defaults to workspace root.
        include_globs: Glob patterns to limit which files are searched
            (e.g. ``"src/**/*.py"``). ``**`` matches recursively. Omit to search all.
        exclude_globs: Glob patterns to exclude. Default excludes (.git, node_modules,
            __pycache__, *.lock) are always applied.
        regex: Treat pattern as regex (default True). If False, literal match.
        case_sensitive: Case-sensitive matching. Default False.
        context: Lines of context before and after each match. Default 2. Set 0 to disable.
        max_results: Cap on returned matches. Default 1000.

    Returns:
        GrepResult: Matches with ``file_path``, ``line_number``, ``line``, and context.
    """
    try:
        # Default excludes that are always applied (globstar semantics)
        default_excludes = [
            ".git/**",
            "node_modules/**",
            "__pycache__/**",
            "**/*.lock",
        ]
        # Merge default excludes with user-provided excludes
        exclude_globs = default_excludes if exclude_globs is None else exclude_globs + default_excludes

        # Resolve the search root (file or directory)
        root_abs = Path(path)
        if not root_abs.exists():
            return GrepResult(
                success=False,
                matches=[],
                truncated=False,
                searched_files=0,
                error="path not found",
            )

        flags = 0
        if not case_sensitive:
            flags |= re.IGNORECASE
        patt = re.compile(pattern if regex else re.escape(pattern), flags)
        ctx = max(0, context)

        matches: list[GrepMatch] = []
        searched = 0

        # Single file: search it directly, skip glob filtering
        if root_abs.is_file():
            file_iter = iter([root_abs])
        else:
            file_iter = _apply_globs(_iter_files(root_abs), root_abs, include_globs, exclude_globs)

        for fpath in file_iter:
            try:
                if is_binary_file(fpath):
                    continue
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:  # pragma: no cover - defensive
                logger.warning("Skipping unreadable file %s", fpath)
                continue
            searched += 1
            all_lines = text.splitlines(keepends=False)
            file_display = str(fpath)
            for i, line in enumerate(all_lines):
                if patt.search(line):
                    before = all_lines[max(0, i - ctx) : i] if ctx > 0 else None
                    after = all_lines[i + 1 : i + 1 + ctx] if ctx > 0 else None
                    matches.append(
                        GrepMatch(
                            file_path=file_display,
                            line_number=i + 1,
                            line=line,
                            context_before=before,
                            context_after=after,
                        )
                    )
                    if max_results is not None and len(matches) >= max_results:
                        return GrepResult(
                            success=True,
                            matches=matches,
                            truncated=True,
                            searched_files=searched,
                        )

        return GrepResult(success=True, matches=matches, truncated=False, searched_files=searched)
    except OSError:  # pragma: no cover - defensive
        logger.exception("grep failed")
        return GrepResult(
            success=False,
            matches=[],
            truncated=False,
            searched_files=0,
            error="grep failed",
        )
