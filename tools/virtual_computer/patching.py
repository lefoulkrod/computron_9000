"""Text patch application utilities (structured + unified diff)."""

import difflib
import logging

from ._fs_internal import read_text_lines, write_text_lines
from ._path_utils import resolve_under_home
from .models import ApplyPatchResult

logger = logging.getLogger(__name__)


def apply_text_patch(
    path: str, start_line: int, end_line: int, replacement: str
) -> ApplyPatchResult:
    """Apply a single line-based text patch to a file.

    Replaces a range of lines with new content.

    Args:
        path: Path to the target text file (relative or absolute under the
            virtual computer home directory).
        start_line: Starting line number (1-based, inclusive).
        end_line: Ending line number (1-based, inclusive).
        replacement: New text content to replace the specified line range.

    Returns:
        ApplyPatchResult: Result indicating success, relative ``file_path``,
        and a unified ``diff`` string of the changes when applicable. On
        failure, ``error`` contains a brief message.

    Notes:
        This function writes changes only when a difference is produced. Errors
        such as invalid ranges are reported in the result rather than raised.
    """
    try:
        abs_path, _home, rel = resolve_under_home(path)
        if not abs_path.exists() or not abs_path.is_file():
            return ApplyPatchResult(success=False, file_path=rel, error="File does not exist")

        before_lines = read_text_lines(abs_path)
        after_lines = before_lines.copy()

        if start_line < 1 or end_line < start_line or end_line > len(after_lines):
            return ApplyPatchResult(
                success=False,
                file_path=rel,
                error="Invalid line range",
            )
        new_segment = replacement.splitlines(keepends=True)
        after_lines[start_line - 1 : end_line] = new_segment

        if after_lines == before_lines:
            return ApplyPatchResult(success=True, file_path=rel, diff="")

        diff_text = "".join(
            difflib.unified_diff(
                before_lines,
                after_lines,
                fromfile=f"{rel} (before)",
                tofile=f"{rel} (after)",
                # Use default lineterm ("\n") for standard human-friendly diffs
            )
        )
        write_text_lines(abs_path, after_lines)
        return ApplyPatchResult(success=True, file_path=rel, diff=diff_text)
    except (OSError, ValueError) as exc:  # pragma: no cover
        logger.exception("Failed to apply text patch to %s", path)
        return ApplyPatchResult(success=False, file_path=path, error=str(exc))


def apply_unified_diff(patch_text: str) -> list[ApplyPatchResult]:
    """Apply unified diff patches to existing text files.

    The given ``patch_text`` may contain hunks for one or more files. File
    creation and deletion are not supported; attempts to patch non-existent
    files yield error results for those entries.

    Args:
        patch_text: Unified diff text covering one or multiple files.

    Returns:
        list[ApplyPatchResult]: One result per file encountered in the diff,
        reporting success and an optional unified diff of the applied changes,
        or an ``error`` message.
    """
    results: list[ApplyPatchResult] = []
    lines = patch_text.splitlines(keepends=False)
    idx = 0
    current_old: str | None = None
    current_new: str | None = None
    hunks: list[tuple[int, int, int, int, list[str]]] = []

    def parse_range(token: str) -> tuple[int, int]:
        if "," in token:
            start_s, count_s = token.split(",", 1)
            return int(start_s), int(count_s)
        return int(token), 1

    def flush_file() -> None:
        nonlocal current_old, current_new, hunks
        if current_new is None:
            return
        target = current_new
        if target.startswith(("a/", "b/")):
            target = target[2:]
        if target == "/dev/null":
            results.append(
                ApplyPatchResult(
                    success=False,
                    file_path=target,
                    error="File creation/deletion not supported",
                )
            )
        else:
            try:
                abs_path, _home, rel = resolve_under_home(target)
                if not abs_path.exists() or not abs_path.is_file():
                    results.append(
                        ApplyPatchResult(
                            success=False,
                            file_path=rel,
                            error="Target file missing",
                        )
                    )
                else:
                    original = read_text_lines(abs_path)
                    try:
                        patched = _apply_hunks(original, hunks)
                    except ValueError as exc:  # pragma: no cover - error path
                        results.append(
                            ApplyPatchResult(success=False, file_path=rel, error=str(exc))
                        )
                    else:
                        diff_text = "".join(
                            difflib.unified_diff(
                                original,
                                patched,
                                fromfile=f"{rel} (before)",
                                tofile=f"{rel} (after)",
                                # Default lineterm ("\n")
                            )
                        )
                        if diff_text:
                            write_text_lines(abs_path, patched)
                        results.append(
                            ApplyPatchResult(
                                success=True,
                                file_path=rel,
                                diff=diff_text,
                            )
                        )
            except (OSError, ValueError) as exc:  # pragma: no cover
                results.append(ApplyPatchResult(success=False, file_path=target, error=str(exc)))
        current_old = None
        current_new = None
        hunks = []

    while idx < len(lines):
        line = lines[idx]
        if line.startswith("--- ") and idx + 1 < len(lines) and lines[idx + 1].startswith("+++ "):
            flush_file()
            current_old = line.split(maxsplit=1)[1].strip()
            current_new = lines[idx + 1].split(maxsplit=1)[1].strip()
            idx += 2
            continue
        if line.startswith("@@ "):
            header = line
            try:
                parts = header.split()
                old_spec = parts[1]
                new_spec = parts[2]
                if not old_spec.startswith("-") or not new_spec.startswith("+"):
                    msg = "Malformed hunk header"
                    raise ValueError(msg)
                old_start, old_count = parse_range(old_spec[1:])
                new_start, new_count = parse_range(new_spec[1:])
            except (IndexError, ValueError) as exc:
                results.append(
                    ApplyPatchResult(success=False, file_path=current_new or "?", error=str(exc))
                )
                idx += 1
                continue
            idx += 1
            hunk_body: list[str] = []
            while idx < len(lines):
                l2 = lines[idx]
                if l2.startswith(("@@ ", "--- ")):
                    break
                if l2 and l2[0] in {" ", "+", "-"}:
                    hunk_body.append(l2)
                else:
                    break
                idx += 1
            hunks.append((old_start, old_count, new_start, new_count, hunk_body))
            continue
        idx += 1
    flush_file()
    return results


def _apply_hunks(
    original: list[str], hunks: list[tuple[int, int, int, int, list[str]]]
) -> list[str]:
    """Apply parsed hunks to an original list of lines.

    Args:
        original: The original file content as a list of lines (with newlines).
        hunks: Parsed hunk tuples of the form ``(old_start, old_count,
            new_start, new_count, hunk_body)`` where ``hunk_body`` contains
            lines prefixed with one of ``' '`` (context), ``'-'`` (removal), or
            ``'+'`` (addition).

    Returns:
        list[str]: The patched file content as a list of lines.

    Raises:
        ValueError: If a hunk cannot be applied due to invalid ranges or
            mismatched context.
    """
    result: list[str] = []
    orig_pos = 0
    for old_start, _old_count, _new_start, _new_count, body in hunks:
        pre_index = old_start - 1
        if pre_index < 0:
            msg = "Invalid hunk start"
            raise ValueError(msg)
        if pre_index > len(original):
            msg = "Hunk starts beyond EOF"
            raise ValueError(msg)
        result.extend(original[orig_pos:pre_index])
        orig_line_index = pre_index
        removed = 0
        for line in body:
            tag = line[:1]
            content = line[1:] + "\n" if not line.endswith("\n") else line[1:]
            if tag == " ":
                if orig_line_index >= len(original) or original[orig_line_index] != content:
                    msg = "Context mismatch applying hunk"
                    raise ValueError(msg)
                result.append(content)
                orig_line_index += 1
            elif tag == "-":
                if orig_line_index >= len(original) or original[orig_line_index] != content:
                    msg = "Removal mismatch applying hunk"
                    raise ValueError(msg)
                orig_line_index += 1
                removed += 1
            elif tag == "+":
                result.append(content)
            else:
                msg = "Unknown hunk line prefix"
                raise ValueError(msg)
        orig_pos = orig_line_index
    result.extend(original[orig_pos:])
    return result
