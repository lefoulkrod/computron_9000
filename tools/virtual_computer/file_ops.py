"""High-level file system operations (write/read/move/etc)."""

from __future__ import annotations

import base64
import logging
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from ._fs_internal import is_binary_file
from ._path_utils import resolve_under_home
from .models import (
    DirectoryReadResult,
    DirEntry,
    FileReadResult,
    MakeDirsResult,
    MoveCopyResult,
    PathExistsResult,
    ReadFileError,
    ReadResult,
    RemovePathResult,
    WriteFileResult,
)

logger = logging.getLogger(__name__)


def write_file(path: str, content: str) -> WriteFileResult:
    """Write a UTF-8 text file within the virtual computer home directory.

    Overwrites the file if it already exists and creates parent directories as
    needed. Accepts text only and writes using UTF-8. For binary data, encode
    to text (e.g., base64) before writing. This function does not raise on I/O
    errors; failures are reported in the returned ``WriteFileResult``.

    Args:
        path: Relative or absolute path under the configured home directory.
            The returned path in the result is normalized to be relative to the
            home directory.
        content: UTF-8 text to write. Only ``str`` is accepted.

    Returns:
        WriteFileResult: Result object indicating success or failure. On
        success, ``file_path`` contains the relative path written. On failure,
        ``error`` contains a message.
    """
    file_path: Path | None = None
    rel_return_path: str = ""
    try:
        file_path, _home, rel_return_path = resolve_under_home(path)
        if file_path.parent and not file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            with file_path.open("w", encoding="utf-8") as f:
                f.write(content)
        else:
            logger.error("Content must be of type str, got %s", type(content))
            return WriteFileResult(
                success=False,
                file_path=rel_return_path,
                error=str(type(content)),
            )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Failed to write file at path %s", path)
        err_path = rel_return_path if rel_return_path else path
        return WriteFileResult(success=False, file_path=err_path, error=str(exc))
    logger.debug("Wrote file at path %s", rel_return_path)
    return WriteFileResult(success=True, file_path=rel_return_path)


def make_dirs(path: str) -> MakeDirsResult:
    """Create a directory (and any missing parents) under the home directory.

    Args:
        path: Relative or absolute directory path under the configured home
            directory to create.

    Returns:
        MakeDirsResult: Result object with ``success`` and the created
        directory path (relative to home). ``error`` is set on failure.
    """
    try:
        abs_path, _home, rel = resolve_under_home(path)
        abs_path.mkdir(parents=True, exist_ok=True)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to create directories at path %s", path)
        return MakeDirsResult(success=False, dir_path=path, error="mkdir failed")
    else:
        return MakeDirsResult(success=True, dir_path=rel)


def remove_path(path: str) -> RemovePathResult:
    """Remove a file or directory recursively if present.

    Args:
        path: Relative or absolute path (under the home directory) to remove.

    Returns:
        RemovePathResult: Result object indicating success or failure. On
        success, ``path`` is the relative path removed (or that did not exist).
        On failure, ``error`` contains a message.
    """
    try:
        abs_path, _home, rel = resolve_under_home(path)
        if not abs_path.exists():
            return RemovePathResult(success=True, path=rel)
        if abs_path.is_file() or abs_path.is_symlink():
            abs_path.unlink(missing_ok=True)
        elif abs_path.is_dir():
            shutil.rmtree(abs_path)
        else:
            return RemovePathResult(success=False, path=rel, error="Unsupported path type")
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to remove path %s", path)
        return RemovePathResult(success=False, path=path, error="remove failed")
    else:
        return RemovePathResult(success=True, path=rel)


def move_path(src: str, dst: str) -> MoveCopyResult:
    """Move a file or directory, creating destination parents as needed.

    Args:
        src: Source path (relative or absolute under the home directory).
        dst: Destination path (relative or absolute under the home directory).

    Returns:
        MoveCopyResult: Result object indicating success or failure. Paths in
        the result are normalized to be relative to the home directory.
    """
    try:
        src_abs, _home, src_rel = resolve_under_home(src)
        dst_abs, _home2, dst_rel = resolve_under_home(dst)
        if dst_abs.parent and not dst_abs.parent.exists():
            dst_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_abs), str(dst_abs))
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to move path from %s to %s", src, dst)
        return MoveCopyResult(success=False, src=src, dst=dst, error="move failed")
    else:
        return MoveCopyResult(success=True, src=src_rel, dst=dst_rel)


def copy_path(src: str, dst: str) -> MoveCopyResult:
    """Copy a file or directory.

    If copying a directory, existing destination contents are merged (similar
    to ``cp -r`` with existing dirs allowed).

    Args:
        src: Source path (relative or absolute under the home directory).
        dst: Destination path (relative or absolute under the home directory).

    Returns:
        MoveCopyResult: Result object indicating success or failure. Paths in
        the result are normalized to be relative to the home directory.
    """
    try:
        src_abs, _home, src_rel = resolve_under_home(src)
        dst_abs, _home2, dst_rel = resolve_under_home(dst)
        if dst_abs.parent and not dst_abs.parent.exists():
            dst_abs.parent.mkdir(parents=True, exist_ok=True)
        if src_abs.is_dir():
            shutil.copytree(src_abs, dst_abs, dirs_exist_ok=True)
        else:
            shutil.copy2(src_abs, dst_abs)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to copy path from %s to %s", src, dst)
        return MoveCopyResult(success=False, src=src, dst=dst, error="copy failed")
    else:
        return MoveCopyResult(success=True, src=src_rel, dst=dst_rel)


def append_to_file(path: str, content: str) -> WriteFileResult:
    """Append UTF-8 text to a file, creating the file and parents if needed.

    Appends text using UTF-8 encoding and returns a ``WriteFileResult``. This function
    does not raise on I/O errors; failures are reported in the returned result object
    with an ``error`` message. Only ``str`` content is accepted; for binary data,
    encode to text (e.g., base64) before calling.

    Args:
        path: Relative or absolute path under the home directory.
        content: Text to append (UTF-8). Only ``str`` is accepted.

    Returns:
        WriteFileResult: Result object indicating success or failure. On success,
        ``file_path`` contains the relative path written. On failure, ``error``
        contains a message.
    """
    file_path: Path | None = None
    rel_return_path: str = ""
    try:
        file_path, _home, rel_return_path = resolve_under_home(path)
        if file_path.parent and not file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            with file_path.open("a", encoding="utf-8") as f:
                f.write(content)
        else:
            logger.error("Content must be of type str, got %s", type(content))
            return WriteFileResult(
                success=False,
                file_path=rel_return_path,
                error=str(type(content)),
            )
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to append file at path %s", path)
        err_path = rel_return_path if rel_return_path else path
        return WriteFileResult(success=False, file_path=err_path, error="append failed")
    logger.debug("Appended to file at path %s", rel_return_path)
    return WriteFileResult(success=True, file_path=rel_return_path)


def prepend_to_file(path: str, content: str) -> WriteFileResult:
    """Prepend UTF-8 text to a file, creating the file if needed.

    Args:
        path: Relative or absolute path under the home directory.
        content: Text to prepend (UTF-8). Only ``str`` is accepted.

    Returns:
        WriteFileResult: Indicates success or failure with the relative ``file_path``.
    """
    file_path: Path | None = None
    rel_return_path: str = ""
    try:
        file_path, _home, rel_return_path = resolve_under_home(path)
        if file_path.parent and not file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)

        if not isinstance(content, str):
            logger.error("Content must be of type str, got %s", type(content))
            return WriteFileResult(
                success=False,
                file_path=rel_return_path,
                error=str(type(content)),
            )

        existing_text = ""
        if file_path.exists():
            try:
                with file_path.open("r", encoding="utf-8", errors="replace") as f:
                    existing_text = f.read()
            except Exception:  # pragma: no cover - defensive
                logger.exception("Failed to read existing file for prepend at path %s", path)
                return WriteFileResult(
                    success=False,
                    file_path=rel_return_path,
                    error="read failed",
                )

        with file_path.open("w", encoding="utf-8") as f:
            f.write(content)
            if existing_text:
                f.write(existing_text)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to prepend file at path %s", path)
        err_path = rel_return_path if rel_return_path else path
        return WriteFileResult(success=False, file_path=err_path, error="prepend failed")
    logger.debug("Prepended to file at path %s", rel_return_path)
    return WriteFileResult(success=True, file_path=rel_return_path)


def write_files(files: list[tuple[str, str]]) -> list[WriteFileResult]:
    """Write multiple text files in a batch.

    Each item is processed independently using ``write_file``.

    Args:
        files: A list of ``(path, content)`` tuples where ``content`` is ``str``
            (written as UTF-8).

    Returns:
        list[WriteFileResult]: A list of results in the same order as inputs.
        Examine individual items for success or error details.
    """
    results: list[WriteFileResult] = []
    for path, content in files:
        if not isinstance(content, str):
            logger.error("Content in write_files must be str, got %s", type(content))
            results.append(WriteFileResult(success=False, file_path=path, error=str(type(content))))
            continue
        results.append(write_file(path, content))
    return results


def path_exists(path: str) -> PathExistsResult:
    """Check whether a path exists and whether it is a file or directory.

    Args:
        path: Relative or absolute path (under the home directory) to check.

    Returns:
        PathExistsResult: Result object containing ``exists``, ``is_file``,
        ``is_dir``, and the normalized relative ``path``.
    """
    try:
        abs_path, _home, rel = resolve_under_home(path)
        exists = abs_path.exists()
        is_file = abs_path.is_file()
        is_dir = abs_path.is_dir()
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to check existence for path %s", path)
        return PathExistsResult(exists=False, is_file=False, is_dir=False, path=path)
    else:
        return PathExistsResult(exists=exists, is_file=is_file, is_dir=is_dir, path=rel)


def _read_file_directory(path: str) -> ReadResult:
    """Read a file (text or base64) or list a directory.

    Internal function that handles both file reading and directory listing.
    For files, binary files are returned base64-encoded with ``encoding`` set to
    ``"base64"``. Text files are returned decoded as UTF-8 with ``encoding`` set
    to ``"utf-8"``. For directories, returns an entry listing.

    Args:
        path: Relative or absolute path (under the home directory) to read.

    Returns:
        ReadResult: ``FileReadResult`` for files or ``DirectoryReadResult`` for
        directories. The ``name`` is the path relative to the home directory.

    Raises:
        ReadFileError: If the path does not exist, is not readable, or is an
            unsupported type.
    """
    try:
        target_path, _home, rel_return_path = resolve_under_home(path)
        if not target_path.exists():
            msg = f"Path does not exist: {rel_return_path}"
            logger.error(msg)
            raise ReadFileError(msg)
        if target_path.is_file():
            if is_binary_file(target_path):
                with target_path.open("rb") as f:
                    content_bytes = f.read()
                content = base64.b64encode(content_bytes).decode("ascii")
                return FileReadResult(name=rel_return_path, content=content, encoding="base64")
            with target_path.open("r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return FileReadResult(name=rel_return_path, content=content, encoding="utf-8")
        if target_path.is_dir():
            entries: list[DirEntry] = [
                DirEntry(name=entry.name, is_file=entry.is_file(), is_dir=entry.is_dir())
                for entry in target_path.iterdir()
            ]
            return DirectoryReadResult(name=rel_return_path, entries=entries)
        msg = f"Path is neither file nor directory: {rel_return_path}"
        logger.error(msg)
        raise ReadFileError(msg)
    except OSError as exc:  # pragma: no cover - defensive
        logger.exception("Failed to read file or directory at path %s", path)
        msg = "Failed to read file or directory."
        raise ReadFileError(msg) from exc


def list_dir(path: str, *, include_hidden: bool = False) -> DirectoryReadResult:
    """List directory contents with optional hidden file filtering.

    Returns a directory listing with entries for files and subdirectories.
    By default, hidden files and directories (those starting with '.') are
    excluded from the results.

    Args:
        path: Relative or absolute path (under the home directory) to list.
        include_hidden: If False, exclude entries starting with '.'.

    Returns:
        DirectoryReadResult: Directory listing with filtered entries.

    Raises:
        ReadFileError: If the path does not exist, is not a directory, or is not readable.
    """
    result = _read_file_directory(path)

    if not isinstance(result, DirectoryReadResult):
        msg = f"Path is not a directory: {result.name}"
        logger.error(msg)
        raise ReadFileError(msg)

    if include_hidden:
        return result

    # Filter out hidden files/directories (those starting with '.')
    filtered_entries = [entry for entry in result.entries if not entry.name.startswith(".")]

    return DirectoryReadResult(name=result.name, entries=filtered_entries)
