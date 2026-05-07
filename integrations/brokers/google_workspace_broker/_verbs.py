"""Verb dispatcher for the Google Workspace broker."""

from __future__ import annotations

import base64
import logging
import mimetypes
import secrets
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

from integrations._rpc import RpcError
from integrations.brokers.google_workspace_broker._calendar_client import CalendarClient
from integrations.brokers.google_workspace_broker._contacts_client import ContactsClient
from integrations.brokers.google_workspace_broker._drive_client import DriveClient, _run_sync
from integrations.brokers.google_workspace_broker._gmail_client import GmailClient
from integrations.permissions import Access, Capability, Permissions

logger = logging.getLogger(__name__)


_VERB_REQUIREMENT: dict[str, tuple[Capability, Access]] = {
    # Drive (read)
    "list_drive_files": (Capability.DRIVE, Access.READ),
    "search_drive_files": (Capability.DRIVE, Access.READ),
    "get_drive_file_metadata": (Capability.DRIVE, Access.READ),
    "export_drive_file": (Capability.DRIVE, Access.READ),
    # Drive (write)
    "upload_drive_file": (Capability.DRIVE, Access.READ_WRITE),
    "create_drive_folder": (Capability.DRIVE, Access.READ_WRITE),
    "update_drive_file": (Capability.DRIVE, Access.READ_WRITE),
    "trash_drive_file": (Capability.DRIVE, Access.READ_WRITE),
    "share_drive_file": (Capability.DRIVE, Access.READ_WRITE),
    # Calendar
    "list_calendars": (Capability.CALENDAR, Access.READ),
    "list_events": (Capability.CALENDAR, Access.READ),
    # Email (Gmail)
    "list_mailboxes": (Capability.EMAIL, Access.READ),
    "list_messages": (Capability.EMAIL, Access.READ),
    "search_messages": (Capability.EMAIL, Access.READ),
    "fetch_message": (Capability.EMAIL, Access.READ),
    "fetch_attachment": (Capability.EMAIL, Access.READ),
    # Contacts
    "list_contacts": (Capability.CONTACTS, Access.READ),
    "search_contacts": (Capability.CONTACTS, Access.READ),
}


_Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class VerbDispatcher:
    """Route one RPC verb call to the right Google API client method."""

    def __init__(
        self,
        creds: Credentials,
        *,
        permissions: Permissions,
        downloads_dir: Path,
    ) -> None:
        self._creds = creds
        self._permissions = permissions
        self._downloads_dir = downloads_dir

        self._drive: DriveClient | None = None
        self._calendar: CalendarClient | None = None
        self._gmail: GmailClient | None = None
        self._contacts: ContactsClient | None = None

        scopes = set(creds.scopes or ())
        if scopes & {
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/drive.file",
        }:
            self._drive = DriveClient(creds)
        if scopes & {
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar.events",
        }:
            self._calendar = CalendarClient(creds)
        if scopes & {
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
        }:
            self._gmail = GmailClient(creds)
        if "https://www.googleapis.com/auth/contacts.readonly" in scopes:
            self._contacts = ContactsClient(creds)

        self._handlers: dict[str, _Handler] = {}
        if self._drive is not None:
            self._handlers["list_drive_files"] = self._handle_list_drive_files
            self._handlers["search_drive_files"] = self._handle_search_drive_files
            self._handlers["get_drive_file_metadata"] = self._handle_get_drive_file_metadata
            self._handlers["export_drive_file"] = self._handle_export_drive_file
            self._handlers["upload_drive_file"] = self._handle_upload_drive_file
            self._handlers["create_drive_folder"] = self._handle_create_drive_folder
            self._handlers["update_drive_file"] = self._handle_update_drive_file
            self._handlers["trash_drive_file"] = self._handle_trash_drive_file
            self._handlers["share_drive_file"] = self._handle_share_drive_file
        if self._calendar is not None:
            self._handlers["list_calendars"] = self._handle_list_calendars
            self._handlers["list_events"] = self._handle_list_events
        if self._gmail is not None:
            self._handlers["list_mailboxes"] = self._handle_list_mailboxes
            self._handlers["list_messages"] = self._handle_list_messages
            self._handlers["search_messages"] = self._handle_search_messages
            self._handlers["fetch_message"] = self._handle_fetch_message
            self._handlers["fetch_attachment"] = self._handle_fetch_attachment
        if self._contacts is not None:
            self._handlers["list_contacts"] = self._handle_list_contacts
            self._handlers["search_contacts"] = self._handle_search_contacts

    async def dispatch(self, verb: str, args: dict[str, Any]) -> dict[str, Any]:
        """Entry point called by the RPC layer for every incoming frame."""
        requirement = _VERB_REQUIREMENT.get(verb)
        if requirement is None:
            msg = f"unknown verb: {verb}"
            raise RpcError("BAD_REQUEST", msg)

        cap, min_access = requirement
        granted = self._permissions.get(cap, Access.OFF)
        if granted < min_access:
            msg = (
                f"verb {verb!r} requires {cap.value}:{min_access.name.lower()}, "
                f"but this integration has {cap.value}:{granted.name.lower()}"
            )
            raise RpcError("PERMISSION_DENIED", msg)

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

    async def _handle_upload_drive_file(self, args: dict[str, Any]) -> dict[str, Any]:
        name = _require_str(args, "name")
        data_b64 = _require_str(args, "data_b64")
        mime_type = _require_str(args, "mime_type")
        parent_id = args.get("parent_id") or None
        try:
            content = base64.b64decode(data_b64)
        except Exception as exc:
            raise RpcError("BAD_REQUEST", f"invalid base64 in data_b64: {exc}") from exc
        try:
            result = await _run_sync(
                self._drive.upload_file, name, content, mime_type, parent_id,
            )
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        return {"file": result}

    async def _handle_create_drive_folder(self, args: dict[str, Any]) -> dict[str, Any]:
        name = _require_str(args, "name")
        parent_id = args.get("parent_id") or None
        try:
            result = await _run_sync(
                self._drive.create_folder, name, parent_id,
            )
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        return {"file": result}

    async def _handle_update_drive_file(self, args: dict[str, Any]) -> dict[str, Any]:
        file_id = _require_str(args, "file_id")
        name = args.get("name") or None
        data_b64 = args.get("data_b64") or None
        mime_type = args.get("mime_type") or None
        if name is None and data_b64 is None:
            raise RpcError("BAD_REQUEST", "update requires 'name' and/or 'data_b64'")
        content: bytes | None = None
        if data_b64 is not None:
            try:
                content = base64.b64decode(data_b64)
            except Exception as exc:
                raise RpcError("BAD_REQUEST", f"invalid base64 in data_b64: {exc}") from exc
        try:
            result = await _run_sync(
                self._drive.update_file, file_id, content, mime_type, name,
            )
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        return {"file": result}

    async def _handle_trash_drive_file(self, args: dict[str, Any]) -> dict[str, Any]:
        file_id = _require_str(args, "file_id")
        try:
            result = await _run_sync(self._drive.trash_file, file_id)
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        return {"file": result}

    async def _handle_share_drive_file(self, args: dict[str, Any]) -> dict[str, Any]:
        file_id = _require_str(args, "file_id")
        role = _require_str(args, "role")
        share_type = _require_str(args, "type")
        if role not in ("reader", "commenter", "writer"):
            raise RpcError("BAD_REQUEST", f"role must be reader, commenter, or writer (got {role!r})")
        if share_type not in ("user", "group", "domain", "anyone"):
            raise RpcError("BAD_REQUEST", f"type must be user, group, domain, or anyone (got {share_type!r})")
        email = args.get("email") or None
        if share_type in ("user", "group") and not email:
            raise RpcError("BAD_REQUEST", f"'email' required when type is {share_type!r}")
        try:
            result = await _run_sync(
                self._drive.share_file, file_id, role, share_type, email,
            )
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        return {"permission": result}

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
        cal_name = await _run_sync(self._resolve_calendar_name, calendar_id)
        result: dict[str, Any] = {"events": events}
        if cal_name:
            result["calendar_name"] = cal_name
        return result

    def _resolve_calendar_name(self, calendar_id: str) -> str | None:
        """Best-effort lookup of a calendar's display name (blocking)."""
        try:
            meta = self._calendar._service.calendarList().get(
                calendarId=calendar_id,
            ).execute()
            return meta.get("summary")
        except HttpError:
            return None

    # --- Gmail handlers ------------------------------------------------------

    async def _handle_list_mailboxes(self, args: dict[str, Any]) -> dict[str, Any]:
        try:
            labels = await _run_sync(self._gmail.list_labels)
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc

        mailboxes = [
            {"name": lab.get("name", ""), "attrs": [lab.get("type", "")]}
            for lab in labels
            if lab.get("name")
        ]
        return {"mailboxes": mailboxes}

    async def _handle_list_messages(self, args: dict[str, Any]) -> dict[str, Any]:
        folder = _require_str(args, "folder")
        limit = _require_int(args, "limit", default=20)
        try:
            headers = await _run_sync(self._gmail.list_messages, folder, limit)
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc

        for h in headers:
            h["folder"] = folder
        return {"headers": headers}

    async def _handle_search_messages(self, args: dict[str, Any]) -> dict[str, Any]:
        folder = _require_str(args, "folder")
        query = _require_str(args, "query")
        limit = _require_int(args, "limit", default=20)
        try:
            headers = await _run_sync(
                self._gmail.search_messages, query, folder, limit,
            )
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc

        for h in headers:
            h["folder"] = folder
        return {"headers": headers}

    async def _handle_fetch_message(self, args: dict[str, Any]) -> dict[str, Any]:
        folder = args.get("folder", "")
        uid = _require_str(args, "uid")
        try:
            message = await _run_sync(self._gmail.get_message, uid)
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        message["header"]["folder"] = folder
        return {"message": message}

    async def _handle_fetch_attachment(self, args: dict[str, Any]) -> dict[str, Any]:
        uid = _require_str(args, "uid")
        attachment_id = _require_str(args, "attachment_id")
        try:
            content, filename, mime_type = await _run_sync(
                self._gmail.get_attachment, uid, attachment_id,
            )
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc

        if not filename:
            ext = mimetypes.guess_extension(mime_type) or ""
            filename = f"attachment_{secrets.token_hex(4)}{ext}"
        path = _write_download(self._downloads_dir, content, filename)
        return {
            "path": str(path),
            "filename": filename,
            "mime_type": mime_type,
            "size": len(content),
        }

    # --- Contacts handlers ---------------------------------------------------

    async def _handle_list_contacts(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = _require_int(args, "limit", default=50)
        try:
            people = await _run_sync(self._contacts.list_contacts, limit)
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        return {"contacts": [_flatten_contact(p) for p in people]}

    async def _handle_search_contacts(self, args: dict[str, Any]) -> dict[str, Any]:
        query = _require_str(args, "query")
        limit = _require_int(args, "limit", default=20)
        try:
            people = await _run_sync(self._contacts.search_contacts, query, limit)
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        return {"contacts": [_flatten_contact(p) for p in people]}


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


def _flatten_contact(person: dict[str, Any]) -> dict[str, Any]:
    """Flatten a People API person resource to a simple dict."""
    names = person.get("names", [])
    name = names[0].get("displayName", "") if names else ""
    emails = [
        e.get("value", "") for e in person.get("emailAddresses", [])
        if e.get("value")
    ]
    phones = [
        p.get("value", "") for p in person.get("phoneNumbers", [])
        if p.get("value")
    ]
    orgs = person.get("organizations", [])
    org = orgs[0].get("name", "") if orgs else ""
    title = orgs[0].get("title", "") if orgs else ""
    return {
        "name": name,
        "emails": emails,
        "phones": phones,
        "organization": org,
        "title": title,
    }
