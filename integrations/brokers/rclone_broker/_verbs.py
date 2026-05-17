"""Verb dispatcher for the rclone broker.

Each verb shells out to ``rclone`` against the ``default:`` remote, which the
supervisor configured entirely through ``RCLONE_CONFIG_DEFAULT_*`` env vars.
Per-capability access (read vs. read+write) is enforced here before the
subprocess runs, the same way the other brokers gate their verbs.
"""

from __future__ import annotations

import asyncio
import base64
import json
import secrets
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from integrations._rpc import RpcError
from integrations.brokers.rclone_broker.types import AboutInfo, DirectoryItem
from integrations.permissions import Access, Capability, Permissions

# What each verb needs. DRIVE everywhere — reads (list/download/etc.) just
# inspect, writes (upload/move/delete/mkdir) mutate the remote.
_VERB_REQUIREMENT: dict[str, tuple[Capability, Access]] = {
    # Canonical verbs (shared with the Google Workspace broker so the agent's
    # Drive tools work uniformly against either backend).
    "drive_list": (Capability.DRIVE, Access.READ),
    "drive_download": (Capability.DRIVE, Access.READ),
    "drive_upload": (Capability.DRIVE, Access.READ_WRITE),
    "drive_mkdir": (Capability.DRIVE, Access.READ_WRITE),
    "drive_move": (Capability.DRIVE, Access.READ_WRITE),
    "drive_delete": (Capability.DRIVE, Access.READ_WRITE),
    # Legacy verbs (kept while the unified tool layer rolls out).
    "list_directory": (Capability.DRIVE, Access.READ),
    "about": (Capability.DRIVE, Access.READ),
    "search": (Capability.DRIVE, Access.READ),
    "cat": (Capability.DRIVE, Access.READ),
    "size": (Capability.DRIVE, Access.READ),
    "copy_from_remote": (Capability.DRIVE, Access.READ),
    "copy_to_remote": (Capability.DRIVE, Access.READ_WRITE),
    "move_from_remote": (Capability.DRIVE, Access.READ_WRITE),
    "move_to_remote": (Capability.DRIVE, Access.READ_WRITE),
    "delete": (Capability.DRIVE, Access.READ_WRITE),
    "mkdir": (Capability.DRIVE, Access.READ_WRITE),
}

# Default cap for `cat` so the agent can't pull an arbitrarily large file into
# a tool result. The agent can copy_from_remote + read_file for anything bigger.
_CAT_DEFAULT_MAX_BYTES = 1_000_000

_Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _validate_remote_path(path: str) -> str:
    """Reject ``..`` traversal in a remote path. Empty string means the root."""
    if ".." in path.split("/"):
        raise RpcError("BAD_REQUEST", "path traversal not allowed")
    return path


def _validate_local_path(path: Path, downloads_dir: Path, agent_home: Path) -> Path:
    """Resolve a local path and require it to sit under an allowed root.

    Allowed: the shared downloads directory (where the broker is meant to drop
    retrieved files for the agent) and the agent's home directory (so uploads
    can name a file the agent created).
    """
    resolved = path.resolve()
    roots = [downloads_dir.resolve(), agent_home.resolve()]
    if not any(resolved == root or root in resolved.parents for root in roots):
        raise RpcError("BAD_REQUEST", f"local path not allowed: {path}")
    return resolved


def _require_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise RpcError("BAD_REQUEST", f"{key!r} required (non-empty string)")
    return value


def _remote(path: str) -> str:
    return f"default:{path}" if path else "default:"


def _join_remote_path(parent: str, name: str) -> str:
    """Join a parent remote path and a leaf name into a single remote path."""
    if not parent:
        return name
    if parent.endswith("/"):
        return parent + name
    return f"{parent}/{name}"


def _rclone_entry(raw: dict[str, Any], parent_path: str) -> dict[str, Any]:
    """Project a single ``rclone lsjson`` entry onto the unified entry shape.

    ``handle`` is the entry's full remote path (joining ``parent_path`` and the
    leaf name), which every other verb on this broker accepts as a reference.
    """
    name = str(raw.get("Name", ""))
    return {
        "name": name,
        "handle": _join_remote_path(parent_path, name),
        "is_dir": bool(raw.get("IsDir", False)),
        "size": int(raw.get("Size", 0) or 0),
        "mime_type": str(raw.get("MimeType", "")),
        "modified": str(raw.get("ModTime", "")),
    }


class VerbDispatcher:
    """Route one RPC verb call to the corresponding rclone invocation."""

    def __init__(
        self,
        *,
        permissions: Permissions,
        downloads_dir: Path,
        agent_home: Path = Path("/home/computron"),
    ) -> None:
        self._permissions = permissions
        self._downloads_dir = downloads_dir
        self._agent_home = agent_home

        self._handlers: dict[str, _Handler] = {
            "drive_list": self._handle_drive_list,
            "drive_download": self._handle_drive_download,
            "drive_upload": self._handle_drive_upload,
            "drive_mkdir": self._handle_drive_mkdir,
            "drive_move": self._handle_drive_move,
            "drive_delete": self._handle_drive_delete,
            "list_directory": self._handle_list_directory,
            "about": self._handle_about,
            "search": self._handle_search,
            "cat": self._handle_cat,
            "size": self._handle_size,
            "copy_from_remote": self._handle_copy_from_remote,
            "copy_to_remote": self._handle_copy_to_remote,
            "move_from_remote": self._handle_move_from_remote,
            "move_to_remote": self._handle_move_to_remote,
            "delete": self._handle_delete,
            "mkdir": self._handle_mkdir,
        }

    async def dispatch(self, verb: str, args: dict[str, Any]) -> dict[str, Any]:
        """Entry point called by the RPC layer for every incoming frame."""
        requirement = _VERB_REQUIREMENT.get(verb)
        if requirement is None:
            raise RpcError("BAD_REQUEST", f"unknown verb: {verb}")

        cap, min_access = requirement
        granted = self._permissions.get(cap, Access.OFF)
        if granted < min_access:
            raise RpcError(
                "PERMISSION_DENIED",
                f"verb {verb!r} requires {cap.value}:{min_access.name.lower()}, "
                f"but this integration has {cap.value}:{granted.name.lower()}",
            )

        handler = self._handlers.get(verb)
        if handler is None:
            raise RpcError("BAD_REQUEST", f"verb not implemented: {verb}")
        return await handler(args)

    # --- rclone subprocess helpers ------------------------------------------

    async def _run_rclone(self, *args: str, check: bool = True) -> tuple[int, str, str]:
        """Run rclone, returning ``(returncode, stdout, stderr)`` as decoded text."""
        proc = await asyncio.create_subprocess_exec(
            "rclone", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        if check and proc.returncode != 0:
            raise RpcError("UPSTREAM", f"rclone error: {err.strip() or out.strip()}")
        return proc.returncode or 0, out, err

    async def _run_rclone_raw(self, *args: str) -> bytes:
        """Run rclone, returning raw stdout bytes (for binary-clean verbs like ``cat``)."""
        proc = await asyncio.create_subprocess_exec(
            "rclone", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace")
            raise RpcError("UPSTREAM", f"rclone error: {err.strip()}")
        return stdout

    # --- canonical handlers (shared shape with the Google Workspace broker) -

    async def _handle_drive_list(self, args: dict[str, Any]) -> dict[str, Any]:
        parent = _validate_remote_path(args.get("handle") or "")
        pattern = args.get("pattern") or ""
        flags = []
        if pattern:
            flags = ["--include", f"*{pattern}*"]
        _, stdout, _ = await self._run_rclone(
            "lsjson", _remote(parent), "--no-mimetype", *flags,
        )
        raw = json.loads(stdout)
        return {"entries": [_rclone_entry(item, parent) for item in raw]}

    async def _handle_drive_download(self, args: dict[str, Any]) -> dict[str, Any]:
        remote_path = _validate_remote_path(_require_str(args, "handle"))
        basename = remote_path.rsplit("/", 1)[-1] or f"download_{secrets.token_hex(8)}"
        self._downloads_dir.mkdir(parents=True, exist_ok=True)
        local_path = self._downloads_dir / basename
        await self._run_rclone("copyto", _remote(remote_path), str(local_path))
        size = local_path.stat().st_size
        return {
            "local_path": str(local_path),
            "filename": basename,
            "mime_type": "",
            "size": size,
        }

    async def _handle_drive_upload(self, args: dict[str, Any]) -> dict[str, Any]:
        parent = _validate_remote_path(args.get("parent_handle") or "")
        name = _require_str(args, "name")
        data_b64 = _require_str(args, "data_b64")
        try:
            content = base64.b64decode(data_b64)
        except Exception as exc:
            raise RpcError("BAD_REQUEST", f"invalid base64 in data_b64: {exc}") from exc
        # Stage the bytes in a temp file under the broker's downloads dir so
        # rclone can copy them up. Cleaned up after the rclone call returns
        # regardless of outcome.
        self._downloads_dir.mkdir(parents=True, exist_ok=True)
        scratch = self._downloads_dir / f".upload_{secrets.token_hex(8)}_{name}"
        try:
            scratch.write_bytes(content)
            dest = _join_remote_path(parent, name)
            await self._run_rclone("copyto", str(scratch), _remote(dest))
        finally:
            scratch.unlink(missing_ok=True)
        return {
            "entry": {
                "name": name,
                "handle": _join_remote_path(parent, name),
                "is_dir": False,
                "size": len(content),
                "mime_type": args.get("mime_type") or "",
                "modified": "",
            },
        }

    async def _handle_drive_mkdir(self, args: dict[str, Any]) -> dict[str, Any]:
        parent = _validate_remote_path(args.get("parent_handle") or "")
        name = _require_str(args, "name")
        dest = _join_remote_path(parent, name)
        await self._run_rclone("mkdir", _remote(dest))
        return {
            "entry": {
                "name": name,
                "handle": dest,
                "is_dir": True,
                "size": 0,
                "mime_type": "",
                "modified": "",
            },
        }

    async def _handle_drive_move(self, args: dict[str, Any]) -> dict[str, Any]:
        src = _validate_remote_path(_require_str(args, "handle"))
        dest_parent = _validate_remote_path(args.get("dest_parent_handle") or "")
        new_name = args.get("name") or src.rsplit("/", 1)[-1]
        dest = _join_remote_path(dest_parent, new_name)
        await self._run_rclone("moveto", _remote(src), _remote(dest))
        return {
            "entry": {
                "name": new_name,
                "handle": dest,
                "is_dir": False,
                "size": 0,
                "mime_type": "",
                "modified": "",
            },
        }

    async def _handle_drive_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        remote_path = _validate_remote_path(_require_str(args, "handle"))
        rc, out, err = await self._run_rclone(
            "deletefile", _remote(remote_path), check=False,
        )
        if rc != 0:
            combined = (err + out).lower()
            if "is a directory" in combined or "directory not empty" in combined:
                await self._run_rclone("purge", _remote(remote_path))
            else:
                raise RpcError("UPSTREAM", f"rclone error: {err.strip() or out.strip()}")
        return {"deleted": True}

    # --- legacy handlers (kept while the unified tool layer rolls out) ------

    async def _handle_list_directory(self, args: dict[str, Any]) -> dict[str, Any]:
        path = _validate_remote_path(args.get("path", ""))
        _, stdout, _ = await self._run_rclone("lsjson", _remote(path), "--no-mimetype")
        raw = json.loads(stdout)
        items = [
            DirectoryItem(
                name=entry.get("Name", ""),
                size=int(entry.get("Size", 0) or 0),
                is_dir=bool(entry.get("IsDir", False)),
                mod_time=str(entry.get("ModTime", "")),
            )
            for entry in raw
        ]
        return {"items": [i.model_dump() for i in items]}

    async def _handle_about(self, _args: dict[str, Any]) -> dict[str, Any]:
        _, stdout, _ = await self._run_rclone("about", "default:", "--json")
        data = json.loads(stdout)
        return AboutInfo(
            total_bytes=int(data.get("total", 0) or 0),
            used_bytes=int(data.get("used", 0) or 0),
            free_bytes=int(data.get("free", 0) or 0),
        ).model_dump()

    async def _handle_search(self, args: dict[str, Any]) -> dict[str, Any]:
        pattern = _require_str(args, "pattern")
        path = _validate_remote_path(args.get("path", ""))
        # rclone has no `search`; emulate with `lsf -R` + a glob filter.
        _, stdout, _ = await self._run_rclone(
            "lsf", _remote(path), "-R", "--include", pattern,
        )
        matches = [line.strip() for line in stdout.splitlines() if line.strip()]
        return {"matches": matches, "count": len(matches)}

    async def _handle_size(self, args: dict[str, Any]) -> dict[str, Any]:
        path = _validate_remote_path(args.get("path", ""))
        _, stdout, _ = await self._run_rclone("size", _remote(path), "--json")
        data = json.loads(stdout)
        return {"count": int(data.get("count", 0) or 0), "bytes": int(data.get("bytes", 0) or 0)}

    async def _handle_cat(self, args: dict[str, Any]) -> dict[str, Any]:
        remote_path = _validate_remote_path(_require_str(args, "remote_path"))
        max_bytes = args.get("max_bytes", _CAT_DEFAULT_MAX_BYTES)
        if not isinstance(max_bytes, int) or max_bytes <= 0:
            raise RpcError("BAD_REQUEST", "'max_bytes' must be a positive integer")
        data = await self._run_rclone_raw("cat", _remote(remote_path))
        total = len(data)
        truncated = total > max_bytes
        payload = data[:max_bytes] if truncated else data
        return {
            "content": base64.b64encode(payload).decode("ascii"),
            "encoding": "base64",
            "truncated": truncated,
            "size": total,
        }

    async def _handle_copy_from_remote(self, args: dict[str, Any]) -> dict[str, Any]:
        local_path = self._resolve_download_target(args)
        remote_path = _validate_remote_path(_require_str(args, "remote_path"))
        self._downloads_dir.mkdir(parents=True, exist_ok=True)
        await self._run_rclone("copyto", _remote(remote_path), str(local_path))
        return {"local_path": str(local_path), "bytes_copied": local_path.stat().st_size}

    async def _handle_move_from_remote(self, args: dict[str, Any]) -> dict[str, Any]:
        local_path = self._resolve_download_target(args)
        remote_path = _validate_remote_path(_require_str(args, "remote_path"))
        self._downloads_dir.mkdir(parents=True, exist_ok=True)
        await self._run_rclone("moveto", _remote(remote_path), str(local_path))
        return {"local_path": str(local_path), "bytes_moved": local_path.stat().st_size}

    async def _handle_copy_to_remote(self, args: dict[str, Any]) -> dict[str, Any]:
        local_path = _validate_local_path(
            Path(_require_str(args, "local_path")), self._downloads_dir, self._agent_home,
        )
        remote_path = _validate_remote_path(_require_str(args, "remote_path"))
        if not local_path.exists():
            raise RpcError("BAD_REQUEST", f"local file not found: {local_path}")
        await self._run_rclone("copyto", str(local_path), _remote(remote_path))
        return {"remote_path": remote_path, "bytes_copied": local_path.stat().st_size}

    async def _handle_move_to_remote(self, args: dict[str, Any]) -> dict[str, Any]:
        local_path = _validate_local_path(
            Path(_require_str(args, "local_path")), self._downloads_dir, self._agent_home,
        )
        remote_path = _validate_remote_path(_require_str(args, "remote_path"))
        if not local_path.exists():
            raise RpcError("BAD_REQUEST", f"local file not found: {local_path}")
        size = local_path.stat().st_size
        await self._run_rclone("moveto", str(local_path), _remote(remote_path))
        return {"remote_path": remote_path, "bytes_moved": size}

    async def _handle_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        remote_path = _validate_remote_path(_require_str(args, "remote_path"))
        # `deletefile` handles files; if the target is a directory, fall back to `purge`.
        rc, out, err = await self._run_rclone("deletefile", _remote(remote_path), check=False)
        if rc != 0:
            combined = (err + out).lower()
            if "is a directory" in combined or "directory not empty" in combined:
                await self._run_rclone("purge", _remote(remote_path))
            else:
                raise RpcError("UPSTREAM", f"rclone error: {err.strip() or out.strip()}")
        return {"deleted": True}

    async def _handle_mkdir(self, args: dict[str, Any]) -> dict[str, Any]:
        remote_path = _validate_remote_path(_require_str(args, "remote_path"))
        await self._run_rclone("mkdir", _remote(remote_path))
        return {"created": True}

    # --- internals ----------------------------------------------------------

    def _resolve_download_target(self, args: dict[str, Any]) -> Path:
        """Pick the local destination for a *_from_remote verb.

        Honors an explicit ``local_path`` (validated) or derives a name under
        the shared downloads directory from the remote file's basename.
        """
        explicit = args.get("local_path")
        if isinstance(explicit, str) and explicit:
            return _validate_local_path(Path(explicit), self._downloads_dir, self._agent_home)
        remote_path = _validate_remote_path(_require_str(args, "remote_path"))
        basename = remote_path.rsplit("/", 1)[-1] or f"download_{secrets.token_hex(8)}"
        return self._downloads_dir / basename
