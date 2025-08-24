# Virtual Computer Refactor Plan

This document proposes organization, API, and behavior improvements for `tools/virtual_computer`. It groups changes by theme, calls out overlaps and gaps, and provides a staged migration plan with test impacts.

## Overview

Goals
- Sharpen public vs private surface and keep a stable import path via `tools.virtual_computer`.
- Make APIs consistent (sync vs async, flags, results, logging).
- Fill a few ergonomic gaps (batch ops, previews, search context/excludes).
- Keep changes low-risk and test-driven.

Non-goals
- Large architectural shifts (e.g., async FS everywhere) unless explicitly noted with migration path.

---

## Structure and module layout

Public modules (unchanged filenames)
- `__init__.py` (facade; authoritative exports via `__all__`)
- `models.py` (Pydantic models and custom exceptions)
- `file_ops.py` (write/append/mkdir/move/copy/remove/path_exists/read_file_directory)
- `read_ops.py` (text reads: full/range/head/tail)
- `edit_ops.py` (replace/insert)
- `search_ops.py` (grep)
- `stat_ops.py` (thin wrappers around `path_exists`)
- `patching.py` (structured and unified-diff patching)
- `run_bash_cmd.py` (guarded container command execution)

Private internals (rename for clarity)
- Rename `ops_internal.py` → `_fs_internal.py` (IO helpers: read/write lines, binary sniff).
- Rename `path_utils.py` → `_path_utils.py` (resolution/sanitization helpers).

Workspace state
- Keep `workspace.py` public API (`set_workspace_folder`, `get_current_workspace_folder`). Internally, migrate storage to a `contextvars.ContextVar` for thread/async-safety, preserving the public function surface.

Documentation
- Add a short “Public API” section to the repo README mirroring `__all__` from `tools.virtual_computer`.

---

## API consistency and behavior

Sync/async
- Make `file_ops.read_file_directory` synchronous. It performs only sync IO and is the lone async FS function.
  - Migration: update tests to call it directly without `await`.
  - Alternative (defer): keep async, but document that it is currently sync under the hood.

Edit flags parity
- `edit_ops.insert_text` should support `preview_only` to mirror `replace_in_file`.
  - Behavior: when `preview_only=True`, apply in memory, return counts, do not write.

Case-sensitivity options
- Add `case_sensitive: bool = True` to `replace_in_file` and `insert_text`:
  - For regex mode: add/remove `re.IGNORECASE` accordingly.
  - For literal mode: match exactly (documented). Optionally add `ignore_case` literal matching later if needed.

Result model base
- Introduce `BaseResult(BaseModel)` with `success: bool` and `error: str | None = None`.
- Inherit existing result models from `BaseResult` to unify and reduce duplication (no wire changes to field names).

Logging and docstrings
- Ensure parameterized logging only (no f-strings in logging calls).
- Use concise Google-style docstrings across modules (Args/Returns/Raises).

---

## Overlaps and clarifications

Stat wrappers
- Keep `stat_ops.exists/is_file/is_dir` as convenience aliases over `file_ops.path_exists`.
- Docstrings should clearly state they are thin wrappers for ergonomics.

Read API split
- Guidance: use `read_ops.read_file` for text-only with optional ranges (rejects binary).
- Use `file_ops.read_file_directory` to read binary files (base64) or list directories.

Bash command policy
- `_ALLOWED_PREFIXES` in `run_bash_cmd.py` is currently unused. Either remove it to avoid confusion, or implement an explicit allow+deny policy. Recommendation: remove (tests assert deny-list behavior only).

---

## Search improvements

Defaults and options
- Add `max_file_bytes: int | None` to skip excessively large files.
- Add `grep_context(pattern, before=0, after=0, ...)` variant returning context lines.

---

## New ergonomic tools

- `list_dir(path: str, include_hidden: bool = False) -> DirectoryReadResult`
  - Thin explicit wrapper around directory branch of `read_file_directory`.
- `glob_paths(patterns: list[str], base: str = ".") -> list[str]`
  - Workspace-safe globbing with clamped traversal.
- `batch_replace(files: list[str], pattern: str, replacement: str, ...) -> list[ReplaceInFileResult]`
  - Multi-file replace helper built on `replace_in_file`.
- `insert_text(..., preview_only: bool = False)`
  - Parity with replace preview.
- `apply_unified_diff_preview(patch_text: str) -> list[ApplyPatchResult]`
  - Compute diffs without writing; useful for dry-runs and reviews.
- `read_file(..., max_bytes: int | None = None, max_lines: int | None = None)`
  - Bound memory/output; add `truncated: bool` in `ReadTextResult`.
- Optional JSON/YAML helpers (paired with Pydantic): `read_json/write_json`.

---

## Patching refinements

- `apply_unified_diff` optionally normalize CR/LF and document behavior.
- Add “verify-only” mode that reports mismatch or no-op without writing.

---

## Tests: additions and updates

Updates (if applied)
- Drop `await` for `read_file_directory` and associated tests.
- Add coverage for `insert_text(preview_only=True)`.

New tests
- `file_ops.move_path` and `copy_path`: happy path + error path.
- `_path_utils.resolve_under_home`: container prefix mapping, deep `..` clamping, trailing slashes.
- `search_ops.grep`: default excludes, `max_file_bytes`, and `grep_context` behavior.
- `run_bash_cmd`: ensure `_ALLOWED_PREFIXES` removal doesn’t change behavior; maintain deny-list tests.

---

## Staged migration plan

Phase 1 (Low-risk, quick wins)
- Add `preview_only` to `insert_text`.
- Remove dead `_ALLOWED_PREFIXES` in `run_bash_cmd.py`.
- Add default exclude support to `grep` behind `use_default_excludes=True` (default True).
- Tighten logging/docstrings to standard.

Phase 2 (Consistency)
- Convert `read_file_directory` to sync function and update tests.
- Introduce `BaseResult` and migrate models to inherit (no field rename).
- Add `case_sensitive` flags to `replace_in_file`/`insert_text`.

Phase 3 (Ergonomics)
- Implement `list_dir`, `glob_paths`, `batch_replace`, `grep_context`.
- Add `max_bytes/max_lines` to `read_file` with `truncated` flag.

Phase 4 (Internals)
- Rename internal modules to `_fs_internal.py` and `_path_utils.py`.
- Switch `workspace` state to `ContextVar`, keep public functions intact.

---

## Backward compatibility notes

- Imports via `from tools.virtual_computer import ...` remain stable; `__init__.__all__` is the single source of truth.
- If/when `read_file_directory` becomes sync, the only breaking change is removing `await` at call sites (tests and any runtime callers).
- Model inheritance from `BaseResult` does not change wire shape (JSON remains the same).

---

## Open questions

- Should `replace_in_file`/`insert_text` support multi-line anchors with DOTALL by default or keep line-oriented semantics?
- For `grep`, how aggressive should default excludes be (e.g., `dist/**`, `.venv/**`)? Make it configurable per repo?
- `run_bash_cmd`: prefer return-only errors (no raising) with a `strict` toggle, or keep current raising for timeouts/container missing?

---

## Acceptance criteria

- Clear public/private split; `__init__` exports documented.
- Consistent edit APIs (preview parity, optional case-sensitivity).
- Search defaults avoid noisy/vendor trees while remaining overridable.
- Tests added/updated to cover behavioral changes and new helpers.
- No changes to on-the-wire JSON field names for existing results.