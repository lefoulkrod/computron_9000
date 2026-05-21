"""Verb dispatcher for the rclone broker.

Each verb is a JSON-RPC call into the broker's long-lived ``rclone rcd``
subprocess via the local UDS. rcd holds the backend config and any
session-acquired cookies in its own process memory; the dispatcher is a
thin shim that maps the agent-facing verb shapes onto rclone's RC API.
"""

from __future__ import annotations

import base64
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from integrations._perms import AGENT_OWNED_FILE_MODE
from integrations._rpc import RpcError
from integrations.brokers.rclone_broker._rcd import RcdAuthError, RcdClient, RcdError
from integrations.permissions import Access, Capability, Permissions

# DRIVE capability everywhere — read verbs need at least READ; mutators need
# READ_WRITE. The names match the Google Workspace broker's canonical verbs
# so the unified Drive tool layer is backend-agnostic.
_VERB_REQUIREMENT: dict[str, tuple[Capability, Access]] = {
    "drive_list": (Capability.DRIVE, Access.READ),
    "drive_download": (Capability.DRIVE, Access.READ),
    "drive_upload": (Capability.DRIVE, Access.READ_WRITE),
    "drive_mkdir": (Capability.DRIVE, Access.READ_WRITE),
    "drive_move": (Capability.DRIVE, Access.READ_WRITE),
    "drive_delete": (Capability.DRIVE, Access.READ_WRITE),
}

_REMOTE_NAME = "default"
_REMOTE_FS = f"{_REMOTE_NAME}:"

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


def _join_remote_path(parent: str, name: str) -> str:
    """Join a parent remote path and a leaf name into a single remote path."""
    if not parent:
        return name
    if parent.endswith("/"):
        return parent + name
    return f"{parent}/{name}"


def _rcd_entry(raw: dict[str, Any], parent_path: str) -> dict[str, Any]:
    """Project one ``operations/list`` entry onto the unified entry shape."""
    name = str(raw.get("Name", ""))
    return {
        "name": name,
        "handle": _join_remote_path(parent_path, name),
        "is_dir": bool(raw.get("IsDir", False)),
        "size": int(raw.get("Size", 0) or 0),
        "mime_type": str(raw.get("MimeType", "")),
        "modified": str(raw.get("ModTime", "")),
    }


def _map_rcd_error(exc: RcdError) -> RpcError:
    """Translate an :class:`RcdError` into an :class:`RpcError` for the wire."""
    if isinstance(exc, RcdAuthError):
        return RpcError("AUTH", str(exc))
    return RpcError("UPSTREAM", str(exc))


class VerbDispatcher:
    """Route one RPC verb call to the corresponding rcd JSON-RPC call."""

    def __init__(
        self,
        *,
        permissions: Permissions,
        rcd: RcdClient,
        downloads_dir: Path,
    ) -> None:
        self._permissions = permissions
        self._rcd = rcd
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
        try:
            return await handler(args)
        except RcdError as exc:
            raise _map_rcd_error(exc) from exc

    # --- handlers -----------------------------------------------------------

    async def _handle_drive_list(self, args: dict[str, Any]) -> dict[str, Any]:
        parent = _validate_remote_path(args.get("handle") or "")
        pattern = (args.get("pattern") or "").lower()
        limit_raw = args.get("limit", 50)
        limit = int(limit_raw) if isinstance(limit_raw, int) else 50
        result = await self._rcd.call(
            "operations/list",
            {"fs": _REMOTE_FS, "remote": parent},
        )
        items = result.get("list", [])
        if pattern:
            items = [
                item for item in items
                if pattern in str(item.get("Name", "")).lower()
            ]
        items = items[: max(0, limit)]
        return {"entries": [_rcd_entry(item, parent) for item in items]}

    async def _handle_drive_download(self, args: dict[str, Any]) -> dict[str, Any]:
        remote_path = _validate_remote_path(_require_str(args, "handle"))
        basename = remote_path.rsplit("/", 1)[-1] or "download"
        self._downloads_dir.mkdir(parents=True, exist_ok=True)
        # `dstFs` must end with a trailing slash so rclone treats it as a
        # filesystem root rather than a single-file destination.
        await self._rcd.call(
            "operations/copyfile",
            {
                "srcFs": _REMOTE_FS,
                "srcRemote": remote_path,
                "dstFs": str(self._downloads_dir) + "/",
                "dstRemote": basename,
            },
        )
        local_path = self._downloads_dir / basename
        # rcd inherits our process umask (0o077) so the file lands at 0o600.
        # Hand the file over to the agent: the agent's uid is in the broker
        # group, so group rw lets it read, modify, and (with the parent dir's
        # AGENT_OWNED_DIR_MODE) delete the file. The broker's job ends here.
        if local_path.exists():
            local_path.chmod(AGENT_OWNED_FILE_MODE)
        return {
            "local_path": str(local_path),
            "filename": basename,
            "mime_type": "",
            "size": local_path.stat().st_size if local_path.exists() else 0,
        }

    async def _handle_drive_upload(self, args: dict[str, Any]) -> dict[str, Any]:
        parent = _validate_remote_path(args.get("parent_handle") or "")
        name = _require_str(args, "name")
        data_b64 = _require_str(args, "data_b64")
        try:
            content = base64.b64decode(data_b64)
        except (ValueError, TypeError) as exc:
            raise RpcError("BAD_REQUEST", f"invalid base64 in data_b64: {exc}") from exc
        mime_type = args.get("mime_type") or "application/octet-stream"
        await self._rcd.upload_file(
            parent_path=parent, filename=name, content=content, mime_type=mime_type,
        )
        return {
            "entry": {
                "name": name,
                "handle": _join_remote_path(parent, name),
                "is_dir": False,
                "size": len(content),
                "mime_type": mime_type,
                "modified": "",
            },
        }

    async def _handle_drive_mkdir(self, args: dict[str, Any]) -> dict[str, Any]:
        parent = _validate_remote_path(args.get("parent_handle") or "")
        name = _require_str(args, "name")
        dest = _join_remote_path(parent, name)
        await self._rcd.call("operations/mkdir", {"fs": _REMOTE_FS, "remote": dest})
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
        await self._rcd.call(
            "operations/movefile",
            {
                "srcFs": _REMOTE_FS, "srcRemote": src,
                "dstFs": _REMOTE_FS, "dstRemote": dest,
            },
        )
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
        # Try deletefile first; if rcd reports it's a directory, fall back to purge.
        try:
            await self._rcd.call(
                "operations/deletefile",
                {"fs": _REMOTE_FS, "remote": remote_path},
            )
        except RcdError as exc:
            text = str(exc).lower()
            if "is a directory" in text or "directory not empty" in text:
                await self._rcd.call(
                    "operations/purge",
                    {"fs": _REMOTE_FS, "remote": remote_path},
                )
            else:
                raise
        return {"deleted": True}
