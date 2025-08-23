"""Pydantic models and type definitions for virtual computer file system operations.

Separated from the monolithic file_system module to keep responsibilities focused.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WriteFileResult(BaseModel):
    """Model returned by write/append operations."""

    success: bool
    file_path: str
    error: str | None = None


class MakeDirsResult(BaseModel):
    """Model returned by make_dirs."""

    success: bool
    dir_path: str
    error: str | None = None


class RemovePathResult(BaseModel):
    """Model returned by remove_path."""

    success: bool
    path: str
    error: str | None = None


class MoveCopyResult(BaseModel):
    """Model returned by move_path and copy_path."""

    success: bool
    src: str
    dst: str
    error: str | None = None


class PathExistsResult(BaseModel):
    """Model returned by path_exists."""

    exists: bool
    is_file: bool
    is_dir: bool
    path: str


class ReadFileError(Exception):
    """Custom exception for errors during file reading operations."""


class DirEntry(BaseModel):
    """Directory entry for a file or subdirectory."""

    name: str
    is_file: bool
    is_dir: bool


class FileReadResult(BaseModel):
    """Return type for reading a file."""

    type: Literal["file"] = Field(default="file", frozen=True)
    name: str
    content: str
    encoding: Literal["utf-8", "base64"]


class DirectoryReadResult(BaseModel):
    """Return type for reading a directory."""

    type: Literal["directory"] = Field(default="directory", frozen=True)
    name: str
    entries: list[DirEntry]


ReadResult = FileReadResult | DirectoryReadResult


class TextPatch(BaseModel):
    """Single text patch operation (line range or substring)."""

    start_line: int | None = None
    end_line: int | None = None
    original: str | None = None
    replacement: str

    def mode(self) -> str:  # pragma: no cover - trivial
        """Return patch mode ("lines" or "substring")."""
        if self.start_line is not None or self.end_line is not None:
            return "lines"
        return "substring"


class ApplyPatchResult(BaseModel):
    """Result of applying a patch to a file."""

    success: bool
    file_path: str
    diff: str | None = None
    error: str | None = None


# --- New results for read/search/edit ops -------------------------------------------------------


class ReadTextResult(BaseModel):
    """Result of reading text from a file, optionally by line range.

    Args:
        success: Whether the read was successful.
        file_path: Path relative to the virtual computer home directory.
        content: File content or selected range as a single UTF-8 string.
        start: Optional inclusive start line (1-based).
        end: Optional inclusive end line (1-based).
        total_lines: Total number of lines in the file when known.
        error: Optional error message on failure.

    Returns:
        ReadTextResult: JSON-serializable read result.

    Raises:
        None
    """

    success: bool
    file_path: str
    content: str | None
    start: int | None = None
    end: int | None = None
    total_lines: int | None = None
    error: str | None = None


class GrepMatch(BaseModel):
    """Single grep match within a file."""

    file_path: str
    line_number: int
    line: str
    start_col: int
    end_col: int


class GrepResult(BaseModel):
    """Result of a grep search across files in the workspace."""

    success: bool
    matches: list[GrepMatch]
    truncated: bool = False
    searched_files: int = 0
    error: str | None = None


class ReplaceInFileResult(BaseModel):
    """Result of a replace-in-file operation."""

    success: bool
    file_path: str
    replacements: int
    preview: bool
    diff_sample: str | None = None
    error: str | None = None


class InsertTextResult(BaseModel):
    """Result of inserting text relative to an anchor pattern."""

    success: bool
    file_path: str
    occurrences: int
    where: str
    error: str | None = None
