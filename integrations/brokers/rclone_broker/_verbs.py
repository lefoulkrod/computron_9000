"""Verb dispatcher for the rclone broker."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import secrets
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

from integrations._rpc import RpcError
from integrations.brokers.rclone_broker.types import AboutInfo, DirectoryItem

_VERB_TYPE: dict[str, Literal["read", "write"]] = {
    "list_directory": "read",
    "about": "read",
    "search": "read",
    "cat": "read",
    "size": "read",
    "copy_from_remote": "read",
    "copy_to_remote": "write",
    "move_from_remote": "write",
    "move_to_remote": "write",
    "delete": "write",
    "mkdir": "write",
}

_Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _validate_remote_path(path: str) -> str:
    """Validate a remote path — no '..' traversal."""
    if ".." in path.split("/"):
        raise RpcError("BAD_REQUEST", "path traversal not allowed")
    return path


def _validate_local_path(path: Path, downloads_dir: Path) -> Path:
    """Validate a local path is within allowed directories."""
    resolved = path.resolve()
    allowed_roots = [downloads_dir.resolve(), Path("/home/computron").resolve()]
    if not any(str(resolved).startswith(str(root)) for root in allowed_roots):
        raise RpcError("BAD_REQUEST", f"local path not allowed: {path}")
    return resolved


class VerbDispatcher:
    def __init__(
        self,
        *,
        write_allowed: bool,
        downloads_dir: Path,
    ) -> None:
        self._write_allowed = write_allowed
        self._downloads_dir = downloads_dir

        self._handlers: dict[str, _Handler] = {
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
        verb_type = _VERB_TYPE.get(verb)
        if verb_type is None:
            msg = f"unknown verb: {verb}"
            raise RpcError("BAD_REQUEST", msg)

        if verb_type == "write" and not self._write_allowed:
            msg = "writes disabled for this integration"
            raise RpcError("WRITE_DENIED", msg)

        handler = self._handlers.get(verb)
        if handler is None:
            msg = f"verb not implemented: {verb}"
            raise RpcError("BAD_REQUEST", msg)

        return await handler(args)

    async def _run_rclone(self, *args: str, check: bool = True) -> tuple[int, str, str]:
        """Run rclone and return (returncode, stdout, stderr) as decoded strings."""
        proc = await asyncio.create_subprocess_exec(
            "rclone", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")
        if check and proc.returncode != 0:
            raise RpcError("UPSTREAM", f"rclone error: {stderr_str.strip() or stdout_str.strip()}")
        return proc.returncode, stdout_str, stderr_str

    async def _run_rclone_raw(self, *args: str) -> tuple[int, bytes, str]:
        """Run rclone and return (returncode, raw stdout bytes, stderr string).

        Use this for verbs that need binary-clean stdout (e.g. ``cat``).
        """
        proc = await asyncio.create_subprocess_exec(
            "rclone", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        stderr_str = stderr.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            raise RpcError("UPSTREAM", f"rclone error: {stderr_str.strip()}")
        return proc.returncode, stdout, stderr_str

    # --- handlers ---

    async def _handle_list_directory(self, args: dict[str, Any]) -> dict[str, Any]:
        path = _validate_remote_path(args.get("path", ""))
        remote = f"default:{path}" if path else "default:"
        _, stdout, _ = await self._run_rclone("lsjson", remote, "--no-mimetype")
        items_raw = json.loads(stdout)
        items = [
            DirectoryItem(
                name=item["Name"] if item.get("IsDir") else item["Name"],
                size=item.get("Size", 0),
                is_dir=item.get("IsDir", False),
                mod_time=item.get("ModTime", ""),
            )
            for item in items_raw
        ]
        return {"items": [i.model_dump() for i in items]}

    async def _handle_about(self, _args: dict[str, Any]) -> dict[str, Any]:
        _, stdout, _ = await self._run_rclone("about", "default:", "--json")
        data = json.loads(stdout)
        info = AboutInfo(
            total_bytes=data.get("total", 0),
            used_bytes=data.get("used", 0),
            free_bytes=data.get("free", 0),
        )
        return info.model_dump()

    async def _handle_copy_from_remote(self, args: dict[str, Any]) -> dict[str, Any]:
        remote_path = _validate_remote_path(_require_str(args, "remote_path"))
        local_path_str = args.get("local_path")
        if local_path_str:
            local_path = _validate_local_path(Path(local_path_str), self._downloads_dir)
        else:
            # Generate a path under downloads
            fname = remote_path.rsplit("/", 1)[-1] if "/" in remote_path else remote_path
            if not fname:
                fname = f"download_{secrets.token_hex(8)}"
            local_path = self._downloads_dir / fname
        
        self._downloads_dir.mkdir(parents=True, exist_ok=True)
        remote = f"default:{remote_path}"
        _, _, _ = await self._run_rclone("copyto", remote, str(local_path))
        size = local_path.stat().st_size
        return {"local_path": str(local_path), "bytes_copied": size}

    async def _handle_copy_to_remote(self, args: dict[str, Any]) -> dict[str, Any]:
        local_path = _validate_local_path(Path(_require_str(args, "local_path")), self._downloads_dir)
        remote_path = _validate_remote_path(_require_str(args, "remote_path"))
        if not local_path.exists():
            raise RpcError("BAD_REQUEST", f"local file not found: {local_path}")
        remote = f"default:{remote_path}"
        _, _, _ = await self._run_rclone("copyto", str(local_path), remote)
        size = local_path.stat().st_size
        return {"bytes_copied": size, "remote_path": remote_path}

    async def _handle_move_from_remote(self, args: dict[str, Any]) -> dict[str, Any]:
        remote_path = _validate_remote_path(_require_str(args, "remote_path"))
        local_path_str = args.get("local_path")
        if local_path_str:
            local_path = _validate_local_path(Path(local_path_str), self._downloads_dir)
        else:
            fname = remote_path.rsplit("/", 1)[-1] if "/" in remote_path else remote_path
            if not fname:
                fname = f"download_{secrets.token_hex(8)}"
            local_path = self._downloads_dir / fname
        
        self._downloads_dir.mkdir(parents=True, exist_ok=True)
        remote = f"default:{remote_path}"
        _, _, _ = await self._run_rclone("moveto", remote, str(local_path))
        size = local_path.stat().st_size
        return {"local_path": str(local_path), "bytes_moved": size}

    async def _handle_move_to_remote(self, args: dict[str, Any]) -> dict[str, Any]:
        local_path = _validate_local_path(Path(_require_str(args, "local_path")), self._downloads_dir)
        remote_path = _validate_remote_path(_require_str(args, "remote_path"))
        if not local_path.exists():
            raise RpcError("BAD_REQUEST", f"local file not found: {local_path}")
        remote = f"default:{remote_path}"
        _, _, _ = await self._run_rclone("moveto", str(local_path), remote)
        size = local_path.stat().st_size
        return {"bytes_moved": size, "remote_path": remote_path}

    async def _handle_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        remote_path = _validate_remote_path(_require_str(args, "remote_path"))
        remote = f"default:{remote_path}"
        # Try deletefile first (for files), fall back to purge (for dirs)
        _, stdout, stderr = await self._run_rclone("deletefile", remote, check=False)
        if "is a directory" in stderr.lower() or "is a directory" in stdout.lower():
            _, _, _ = await self._run_rclone("purge", remote)
        return {"deleted": True}

    async def _handle_mkdir(self, args: dict[str, Any]) -> dict[str, Any]:
        remote_path = _validate_remote_path(_require_str(args, "remote_path"))
        remote = f"default:{remote_path}"
        _, _, _ = await self._run_rclone("mkdir", remote)
        return {"created": True}

    async def _handle_search(self, args: dict[str, Any]) -> dict[str, Any]:
        pattern = _require_str(args, "pattern")
        path = _validate_remote_path(args.get("path", ""))
        remote = f"default:{path}" if path else "default:"
        _, stdout, _ = await self._run_rclone("search", remote, pattern)
        # rclone search outputs one path per line
        lines = [line.strip() for line in stdout.strip().splitlines() if line.strip()]
        return {"matches": lines, "count": len(lines)}

    async def _handle_cat(self, args: dict[str, Any]) -> dict[str, Any]:
        remote_path = _validate_remote_path(_require_str(args, "remote_path"))
        remote = f"default:{remote_path}"
        max_bytes: int = args.get("max_bytes", 1_000_000)  # 1MB default limit
        _, stdout_bytes, _ = await self._run_rclone_raw("cat", remote)
        total_size = len(stdout_bytes)
        truncated = total_size > max_bytes
        content = stdout_bytes[:max_bytes] if truncated else stdout_bytes
        return {
            "content": base64.b64encode(content).decode("ascii"),
            "encoding": "base64",
            "truncated": truncated,
            "size": total_size,
        }

    async def _handle_size(self, args: dict[str, Any]) -> dict[str, Any]:
        path = _validate_remote_path(args.get("path", ""))
        remote = f"default:{path}" if path else "default:"
        _, stdout, _ = await self._run_rclone("size", remote, "--json")
        data = json.loads(stdout)
        return {
            "count": data.get("count", 0),
            "bytes": data.get("bytes", 0),
        }


def _require_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise RpcError("BAD_REQUEST", f"{key!r} required (non-empty string)")
    return value
