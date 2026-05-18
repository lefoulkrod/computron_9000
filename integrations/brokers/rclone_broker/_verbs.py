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
from integrations.permissions import Access, Capability, Permissions

# What each verb needs. DRIVE everywhere — reads (list/download) inspect,
# writes (upload/move/delete/mkdir) mutate the remote. The verb names and
# argument shapes match the Google Workspace broker so the agent's Drive
# tools are backend-agnostic.
_VERB_REQUIREMENT: dict[str, tuple[Capability, Access]] = {
    "drive_list": (Capability.DRIVE, Access.READ),
    "drive_download": (Capability.DRIVE, Access.READ),
    "drive_upload": (Capability.DRIVE, Access.READ_WRITE),
    "drive_mkdir": (Capability.DRIVE, Access.READ_WRITE),
    "drive_move": (Capability.DRIVE, Access.READ_WRITE),
    "drive_delete": (Capability.DRIVE, Access.READ_WRITE),
}

_Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _validate_remote_path(path: str) -> str:
    """Reject ``..`` traversal in a remote path. Empty string means the root."""
    if ".." in path.split("/"):
        raise RpcError("BAD_REQUEST", "path traversal not allowed")
    return path


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
    ) -> None:
        self._permissions = permissions
        self._downloads_dir = downloads_dir

        self._handlers: dict[str, _Handler] = {
            "drive_list": self._handle_drive_list,
            "drive_download": self._handle_drive_download,
            "drive_upload": self._handle_drive_upload,
            "drive_mkdir": self._handle_drive_mkdir,
            "drive_move": self._handle_drive_move,
            "drive_delete": self._handle_drive_delete,
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

    # --- handlers -----------------------------------------------------------

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

