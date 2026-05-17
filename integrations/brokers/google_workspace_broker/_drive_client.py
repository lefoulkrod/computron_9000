"""Google Drive operations via the Drive API v3."""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload, MediaIoBaseDownload

logger = logging.getLogger(__name__)

_FILE_FIELDS = "id, name, mimeType, size, createdTime, modifiedTime, parents, webViewLink"
_LIST_FIELDS = f"nextPageToken, files({_FILE_FIELDS})"

_GOOGLE_DOC_EXPORTS: dict[str, tuple[str, str]] = {
    "application/vnd.google-apps.document": ("text/plain", ".txt"),
    "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
    "application/vnd.google-apps.presentation": ("text/plain", ".txt"),
    "application/vnd.google-apps.drawing": ("image/png", ".png"),
}


class DriveClient:
    """Thin wrapper around the Drive v3 API."""

    def __init__(self, creds: Credentials) -> None:
        self._creds = creds

    def _service(self):  # noqa: ANN202
        return build("drive", "v3", credentials=self._creds, cache_discovery=False)

    def list_files(
        self,
        folder_id: str = "root",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List files in a folder. Returns raw file-resource dicts."""
        q = f"'{folder_id}' in parents and trashed = false"
        results: list[dict[str, Any]] = []
        page_token: str | None = None
        while len(results) < limit:
            page_size = min(limit - len(results), 100)
            resp = (
                self._service().files()
                .list(
                    q=q,
                    fields=_LIST_FIELDS,
                    pageSize=page_size,
                    pageToken=page_token,
                    orderBy="folder,modifiedTime desc",
                )
                .execute()
            )
            results.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return results[:limit]

    def search_files(
        self,
        query: str,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """Search Drive files. ``query`` is a raw Drive API q-string."""
        q = f"{query} and trashed = false"
        results: list[dict[str, Any]] = []
        page_token: str | None = None
        while len(results) < limit:
            page_size = min(limit - len(results), 100)
            resp = (
                self._service().files()
                .list(
                    q=q,
                    fields=_LIST_FIELDS,
                    pageSize=page_size,
                    pageToken=page_token,
                )
                .execute()
            )
            results.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return results[:limit]

    def get_file_metadata(self, file_id: str) -> dict[str, Any]:
        """Get metadata for a single file."""
        return (
            self._service().files()
            .get(fileId=file_id, fields=_FILE_FIELDS)
            .execute()
        )

    def export_file(self, file_id: str) -> tuple[bytes, str, str]:
        """Download or export a file's content.

        For Google Docs/Sheets/Slides, exports to a portable format.
        For binary files, downloads the raw bytes.

        Returns:
            (content_bytes, filename, mime_type)
        """
        meta = self.get_file_metadata(file_id)
        mime = meta.get("mimeType", "")
        name = meta.get("name", file_id)

        if mime in _GOOGLE_DOC_EXPORTS:
            export_mime, ext = _GOOGLE_DOC_EXPORTS[mime]
            buf = io.BytesIO()
            request = self._service().files().export_media(
                fileId=file_id, mimeType=export_mime,
            )
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            content = buf.getvalue()
            export_name = name if name.endswith(ext) else name + ext
            return content, export_name, export_mime

        buf = io.BytesIO()
        request = self._service().files().get_media(fileId=file_id)
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buf.getvalue(), name, mime

    def upload_file(
        self,
        name: str,
        content: bytes,
        mime_type: str,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        """Upload a file to Drive. Returns the created file resource."""
        file_metadata: dict[str, Any] = {"name": name}
        if parent_id:
            file_metadata["parents"] = [parent_id]
        media = MediaInMemoryUpload(content, mimetype=mime_type, resumable=True)
        return (
            self._service().files()
            .create(body=file_metadata, media_body=media, fields=_FILE_FIELDS)
            .execute()
        )

    def create_folder(
        self,
        name: str,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a folder on Drive. Returns the created folder resource."""
        file_metadata: dict[str, Any] = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            file_metadata["parents"] = [parent_id]
        return (
            self._service().files()
            .create(body=file_metadata, fields=_FILE_FIELDS)
            .execute()
        )

    def update_file(
        self,
        file_id: str,
        content: bytes | None = None,
        mime_type: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing file's content and/or name."""
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        kwargs: dict[str, Any] = {"fileId": file_id, "fields": _FILE_FIELDS}
        if body:
            kwargs["body"] = body
        if content is not None:
            mt = mime_type or "application/octet-stream"
            kwargs["media_body"] = MediaInMemoryUpload(
                content, mimetype=mt, resumable=True,
            )
        return self._service().files().update(**kwargs).execute()

    def trash_file(self, file_id: str) -> dict[str, Any]:
        """Move a file to the trash. Returns the updated file resource."""
        return (
            self._service().files()
            .update(fileId=file_id, body={"trashed": True}, fields=_FILE_FIELDS)
            .execute()
        )

    def resolve_path(self, path: str) -> str | None:
        """Walk a slash-separated path from the Drive root and return the leaf's ID.

        Returns ``None`` if any segment is missing. The empty string and ``"/"``
        both resolve to ``"root"``. When two children share a name, the first
        returned by ``files.list`` wins — Drive permits duplicates but they're
        rare; the alternative is an error and the agent has no way to tell which
        one it meant anyway.
        """
        cleaned = path.strip("/")
        if not cleaned:
            return "root"
        parent_id = "root"
        for segment in cleaned.split("/"):
            safe = segment.replace("'", "\\'")
            q = (
                f"'{parent_id}' in parents and trashed = false "
                f"and name = '{safe}'"
            )
            resp = (
                self._service().files()
                .list(q=q, fields="files(id, mimeType)", pageSize=2)
                .execute()
            )
            files = resp.get("files", [])
            if not files:
                return None
            parent_id = files[0]["id"]
        return parent_id

    def list_in_parent_matching(
        self,
        parent_id: str,
        name_substring: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Direct children of ``parent_id`` whose name contains ``name_substring``."""
        safe = name_substring.replace("'", "\\'")
        q = (
            f"'{parent_id}' in parents and trashed = false "
            f"and name contains '{safe}'"
        )
        results: list[dict[str, Any]] = []
        page_token: str | None = None
        while len(results) < limit:
            page_size = min(limit - len(results), 100)
            resp = (
                self._service().files()
                .list(
                    q=q,
                    fields=_LIST_FIELDS,
                    pageSize=page_size,
                    pageToken=page_token,
                    orderBy="folder,modifiedTime desc",
                )
                .execute()
            )
            results.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return results[:limit]

    def move_file(
        self,
        file_id: str,
        new_parent_id: str,
        new_name: str | None = None,
    ) -> dict[str, Any]:
        """Move ``file_id`` into ``new_parent_id`` and optionally rename it."""
        current = (
            self._service().files()
            .get(fileId=file_id, fields="parents")
            .execute()
        )
        old_parents = ",".join(current.get("parents", []))
        body: dict[str, Any] = {}
        if new_name is not None:
            body["name"] = new_name
        kwargs: dict[str, Any] = {
            "fileId": file_id,
            "addParents": new_parent_id,
            "removeParents": old_parents,
            "fields": _FILE_FIELDS,
        }
        if body:
            kwargs["body"] = body
        return self._service().files().update(**kwargs).execute()

    def share_file(
        self,
        file_id: str,
        role: str,
        share_type: str,
        email: str | None = None,
    ) -> dict[str, Any]:
        """Create a permission on a file.

        Args:
            file_id: The file to share.
            role: ``"reader"``, ``"commenter"``, or ``"writer"``.
            share_type: ``"user"``, ``"group"``, ``"domain"``, or ``"anyone"``.
            email: Required when share_type is ``"user"`` or ``"group"``.

        Returns:
            The created permission resource (id, role, type, emailAddress).
        """
        permission: dict[str, str] = {"role": role, "type": share_type}
        if email:
            permission["emailAddress"] = email
        return (
            self._service().permissions()
            .create(
                fileId=file_id,
                body=permission,
                fields="id, role, type, emailAddress",
            )
            .execute()
        )


async def _run_sync(fn, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
    """Run a blocking googleapiclient call on the default executor."""
    return await asyncio.to_thread(fn, *args, **kwargs)

