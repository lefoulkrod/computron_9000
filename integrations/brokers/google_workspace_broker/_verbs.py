"""Verb dispatcher for the Google Workspace broker."""

from __future__ import annotations

import logging
import secrets
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

from integrations._rpc import RpcError
from integrations.brokers.google_workspace_broker._calendar_client import CalendarClient
from integrations.brokers.google_workspace_broker._drive_client import DriveClient, _run_sync

logger = logging.getLogger(__name__)


_VERB_TYPE: dict[str, Literal["read", "write"]] = {
    "list_drive_files": "read",
    "search_drive_files": "read",
    "get_drive_file_metadata": "read",
    "export_drive_file": "read",
    "list_calendars": "read",
    "list_events": "read",
}


_Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class VerbDispatcher:
    """Route one RPC verb call to the right Google API client method."""

    def __init__(
        self,
        creds: Credentials,
        *,
        write_allowed: bool,
        downloads_dir: Path,
    ) -> None:
        self._creds = creds
        self._write_allowed = write_allowed
        self._downloads_dir = downloads_dir

        self._drive: DriveClient | None = None
        self._calendar: CalendarClient | None = None

        scopes = set(creds.scopes or ())
        if "https://www.googleapis.com/auth/drive.readonly" in scopes:
            self._drive = DriveClient(creds)
        if "https://www.googleapis.com/auth/calendar.readonly" in scopes:
            self._calendar = CalendarClient(creds)

        self._handlers: dict[str, _Handler] = {}
        if self._drive is not None:
            self._handlers["list_drive_files"] = self._handle_list_drive_files
            self._handlers["search_drive_files"] = self._handle_search_drive_files
            self._handlers["get_drive_file_metadata"] = self._handle_get_drive_file_metadata
            self._handlers["export_drive_file"] = self._handle_export_drive_file
        if self._calendar is not None:
            self._handlers["list_calendars"] = self._handle_list_calendars
            self._handlers["list_events"] = self._handle_list_events

    async def dispatch(self, verb: str, args: dict[str, Any]) -> dict[str, Any]:
        """Entry point called by the RPC layer for every incoming frame."""
        verb_type = _VERB_TYPE.get(verb)
        if verb_type is None:
            msg = f"unknown verb: {verb}"
            raise RpcError("BAD_REQUEST", msg)

        if verb_type == "write" and not self._write_allowed:
            raise RpcError(
                "WRITE_DENIED",
                f"writes are disabled for this integration; "
                f"verb {verb!r} requires write_allowed=true",
            )

        handler = self._handlers.get(verb)
        if handler is None:
            msg = f"verb not implemented: {verb}"
            raise RpcError("BAD_REQUEST", msg)
        return await handler(args)

    # --- Drive handlers ------------------------------------------------------

    async def _handle_list_drive_files(self, args: dict[str, Any]) -> dict[str, Any]:
        folder_id = args.get("folder_id") or "root"
        limit = _require_int(args, "limit", default=50)
        try:
            files = await _run_sync(self._drive.list_files, folder_id, limit)
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        return {"files": files}

    async def _handle_search_drive_files(self, args: dict[str, Any]) -> dict[str, Any]:
        query = _require_str(args, "query")
        limit = _require_int(args, "limit", default=30)
        try:
            files = await _run_sync(self._drive.search_files, query, limit)
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        return {"files": files}

    async def _handle_get_drive_file_metadata(self, args: dict[str, Any]) -> dict[str, Any]:
        file_id = _require_str(args, "file_id")
        try:
            meta = await _run_sync(self._drive.get_file_metadata, file_id)
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        return {"file": meta}

    async def _handle_export_drive_file(self, args: dict[str, Any]) -> dict[str, Any]:
        file_id = _require_str(args, "file_id")
        try:
            content, filename, mime_type = await _run_sync(
                self._drive.export_file, file_id,
            )
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc

        path = _write_download(self._downloads_dir, content, filename)
        return {
            "path": str(path),
            "filename": filename,
            "mime_type": mime_type,
            "size": len(content),
        }

    # --- Calendar handlers ---------------------------------------------------

    async def _handle_list_calendars(self, args: dict[str, Any]) -> dict[str, Any]:
        try:
            items = await _run_sync(self._calendar.list_calendars)
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc

        calendars = [
            {"name": c.get("summary", "(unnamed)"), "url": c["id"]}
            for c in items
            if "id" in c
        ]
        return {"calendars": calendars}

    async def _handle_list_events(self, args: dict[str, Any]) -> dict[str, Any]:
        calendar_id = _require_str(args, "calendar_url")
        days_forward = _require_int(args, "days_forward", default=30)
        days_back = _require_int(args, "days_back", default=0)
        limit = _require_int(args, "limit", default=50)
        try:
            items = await _run_sync(
                self._calendar.list_events,
                calendar_id,
                days_forward=days_forward,
                days_back=days_back,
                limit=limit,
            )
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc

        events = [_flatten_event(e) for e in items]
        cal_name = self._resolve_calendar_name(calendar_id)
        result: dict[str, Any] = {"events": events}
        if cal_name:
            result["calendar_name"] = cal_name
        return result

    def _resolve_calendar_name(self, calendar_id: str) -> str | None:
        """Best-effort lookup of a calendar's display name."""
        try:
            meta = self._calendar._service.calendarList().get(
                calendarId=calendar_id,
            ).execute()
            return meta.get("summary")
        except HttpError:
            return None


# --- helpers -----------------------------------------------------------------


def _require_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise RpcError("BAD_REQUEST", f"{key!r} required (non-empty string)")
    return value


def _require_int(args: dict[str, Any], key: str, *, default: int) -> int:
    value = args.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RpcError("BAD_REQUEST", f"{key!r} must be an integer")
    return value


def _wrap_http_error(exc: HttpError) -> RpcError:
    status = exc.resp.status if exc.resp else 500
    if status == 404:
        return RpcError("NOT_FOUND", str(exc))
    if status in (401, 403):
        return RpcError("AUTH", str(exc))
    return RpcError("UPSTREAM", str(exc))


def _write_download(dir_path: Path, payload: bytes, filename: str) -> Path:
    """Write downloaded content to disk, deduplicating collisions."""
    dir_path.mkdir(parents=True, exist_ok=True)
    dest = dir_path / filename
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        dest = dir_path / f"{stem}_{secrets.token_hex(4)}{suffix}"
    dest.write_bytes(payload)
    dest.chmod(0o640)
    return dest


def _flatten_event(e: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Google Calendar event to the shape the agent tools expect."""
    start_block = e.get("start", {})
    end_block = e.get("end", {})
    return {
        "uid": e.get("id", ""),
        "summary": e.get("summary", ""),
        "start": start_block.get("dateTime") or start_block.get("date", ""),
        "end": end_block.get("dateTime") or end_block.get("date", ""),
        "location": e.get("location", ""),
    }
