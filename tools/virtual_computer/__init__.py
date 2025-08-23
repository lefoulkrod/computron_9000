"""Virtual computer file system public API.

This module re-exports the public interfaces for file system operations, data
models, and patch application utilities so that callers can simply import from
``tools.virtual_computer``.  The legacy ``file_system`` facade module is being
removed; update imports accordingly:

    from tools.virtual_computer import write_file, read_file_directory

Tests may still import internal modules directly if they need to patch
internals, but production code should rely on these exports.
"""

from .file_ops import (
    append_to_file,
    copy_path,
    make_dirs,
    move_path,
    path_exists,
    read_file_directory,
    remove_path,
    write_file,
    write_files,
)
from .models import (
    ApplyPatchResult,
    DirectoryReadResult,
    DirEntry,
    FileReadResult,
    MakeDirsResult,
    MoveCopyResult,
    PathExistsResult,
    ReadFileError,
    ReadResult,
    RemovePathResult,
    TextPatch,
    WriteFileResult,
)
from .patching import (
    apply_text_patch,
    apply_unified_diff,
)
from .run_bash_cmd import (
    BashCmdResult,
    run_bash_cmd,
)

__all__ = [
    "ApplyPatchResult",
    "BashCmdResult",
    "DirEntry",
    "DirectoryReadResult",
    "FileReadResult",
    "MakeDirsResult",
    "MoveCopyResult",
    "PathExistsResult",
    "ReadFileError",
    "ReadResult",
    "RemovePathResult",
    "TextPatch",
    "WriteFileResult",
    "append_to_file",
    "apply_text_patch",
    "apply_unified_diff",
    "copy_path",
    "make_dirs",
    "move_path",
    "path_exists",
    "read_file_directory",
    "remove_path",
    "run_bash_cmd",
    "write_file",
    "write_files",
]
