"""High-level file system operations (write/read/move/etc)."""

from __future__ import annotations

import base64
import logging
import shutil
from pathlib import Path

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
from .ops_internal import is_binary_file
from .path_utils import resolve_under_home

logger = logging.getLogger(__name__)


def write_file(path: str, content: str | bytes) -> WriteFileResult:
    """Write content under the workspace, overwriting if it exists."""
    file_path: Path | None = None
    rel_return_path: str = ""
    try:
        file_path, _home, rel_return_path = resolve_under_home(path)
        if file_path.parent and not file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            with file_path.open("wb") as f:
                f.write(content)
        elif isinstance(content, str):
            with file_path.open("w", encoding="utf-8") as f:
                f.write(content)
        else:
            logger.error("Content must be of type str or bytes, got %s", type(content))
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
    """Create directories (parents ok)."""
    try:
        abs_path, _home, rel = resolve_under_home(path)
        abs_path.mkdir(parents=True, exist_ok=True)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to create directories at path %s", path)
        return MakeDirsResult(success=False, dir_path=path, error="mkdir failed")
    else:
        return MakeDirsResult(success=True, dir_path=rel)


def remove_path(path: str) -> RemovePathResult:
    """Remove a file or directory recursively if present."""
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
    """Move a file or directory, creating destination parents."""
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
    """Copy a file or directory (dirs merged)."""
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


def append_to_file(path: str, content: str | bytes) -> WriteFileResult:
    """Append content to a file, creating it and parents if missing."""
    file_path: Path | None = None
    rel_return_path: str = ""
    try:
        file_path, _home, rel_return_path = resolve_under_home(path)
        if file_path.parent and not file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            with file_path.open("ab") as f:
                f.write(content)
        elif isinstance(content, str):
            with file_path.open("a", encoding="utf-8") as f:
                f.write(content)
        else:
            logger.error("Content must be of type str or bytes, got %s", type(content))
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


def write_files(files: list[tuple[str, str | bytes]]) -> list[WriteFileResult]:
    """Batch write multiple files."""
    results: list[WriteFileResult] = []
    for path, content in files:
        results.append(write_file(path, content))
    return results


def path_exists(path: str) -> PathExistsResult:
    """Return existence and type info for a path."""
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


async def read_file_directory(path: str) -> ReadResult:
    """Read a file (text/base64) or list a directory."""
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
