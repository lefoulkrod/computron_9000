"""Google Drive read operations via the Drive API v3."""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

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
        self._service = build("drive", "v3", credentials=creds)

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
                self._service.files()
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
                self._service.files()
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
            self._service.files()
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
            request = self._service.files().export_media(
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
        request = self._service.files().get_media(fileId=file_id)
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buf.getvalue(), name, mime


async def _run_sync(fn, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
    """Run a blocking googleapiclient call on the default executor."""
    return await asyncio.to_thread(fn, *args, **kwargs)

