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
