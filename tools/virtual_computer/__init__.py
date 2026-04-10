"""Virtual computer file system public API.

This module re-exports the public interfaces for file system operations, data
models, and patch application utilities so that callers can simply import from
``tools.virtual_computer``.  The legacy ``file_system`` facade module is being
removed; update imports accordingly:

    from tools.virtual_computer import write_file, list_dir

Tests may still import internal modules directly if they need to patch
internals, but production code should rely on these exports.
"""

from .edit_ops import insert_text, replace_in_file
from .file_ops import (
    append_to_file,
    copy_path,
    list_dir,
    make_dirs,
    move_path,
    path_exists,
    prepend_to_file,
    remove_path,
    write_file,
    write_files,
)
from .models import (
    ApplyPatchResult,
    DirectoryReadResult,
    DirEntry,
    FileReadResult,
    GrepMatch,
    GrepResult,
    InsertTextResult,
    MakeDirsResult,
    MoveCopyResult,
    PathExistsResult,
    ReadFileError,
    ReadResult,
    ReadTextResult,
    RemovePathResult,
    ReplaceInFileResult,
    TextPatch,
    WriteFileResult,
)
from .patching import apply_text_patch, apply_unified_diff
from .read_ops import head, read_file, tail
from .search_ops import grep
from .stat_ops import exists, is_dir, is_file

# Deferred imports for modules that import from sdk.events,
# which would otherwise create a circular dependency:
#   tools.virtual_computer.__init__ -> file_output -> agents.sdk.events
#   -> agents.__init__ -> agents.media -> tools.virtual_computer
_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "describe_image": (".describe_image", "describe_image"),
    "send_file": (".file_output", "send_file"),
    "play_audio": (".play_audio", "play_audio"),
    "run_bash_cmd": (".run_bash_cmd", "run_bash_cmd"),
    "BashCmdResult": (".run_bash_cmd", "BashCmdResult"),
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        import importlib

        mod = importlib.import_module(module_path, __package__)
        value = getattr(mod, attr)
        # Cache on the module so __getattr__ is only called once per name
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ApplyPatchResult",
    "BashCmdResult",
    "DirEntry",
    "DirectoryReadResult",
    "FileReadResult",
    "GrepMatch",
    "GrepResult",
    "InsertTextResult",
    "MakeDirsResult",
    "MoveCopyResult",
    "PathExistsResult",
    "ReadFileError",
    "ReadResult",
    "ReadTextResult",
    "RemovePathResult",
    "ReplaceInFileResult",
    "TextPatch",
    "WriteFileResult",
    "append_to_file",
    "apply_text_patch",
    "apply_unified_diff",
    "copy_path",
    "describe_image",
    "exists",
    "grep",
    "head",
    "insert_text",
    "is_dir",
    "is_file",
    "list_dir",
    "make_dirs",
    "move_path",
    "send_file",
    "path_exists",
    "play_audio",
    "prepend_to_file",
    "read_file",
    "remove_path",
    "replace_in_file",
    "run_bash_cmd",
    "tail",
    "write_file",
    "write_files",
]
