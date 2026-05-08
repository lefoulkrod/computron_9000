"""Gmail operations via the Gmail API v1."""

from __future__ import annotations

import base64
import email.encoders
import email.mime.base
import email.mime.multipart
import email.mime.text
import logging
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


class GmailClient:
    """Thin wrapper around the Gmail v1 API."""

    def __init__(self, creds: Credentials) -> None:
        self._service = build("gmail", "v1", credentials=creds)
        self._label_cache: dict[str, str] | None = None

    def list_labels(self) -> list[dict[str, Any]]:
        """List all labels visible to the user."""
        resp = self._service.users().labels().list(userId="me").execute()
        labels = resp.get("labels", [])
        self._label_cache = {l["name"]: l["id"] for l in labels if "name" in l and "id" in l}
        return labels

    def _resolve_label_id(self, name: str) -> str:
        """Map a human-readable label name to its Gmail label ID."""
        if self._label_cache is None:
            self.list_labels()
        label_id = self._label_cache.get(name)
        if label_id is None:
            logger.warning("Gmail label %r not found, passing as-is", name)
            return name
        return label_id

    def list_messages(
        self,
        label_name: str = "INBOX",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List recent messages under a label, with headers."""
        label_id = self._resolve_label_id(label_name)
        message_ids = self._list_message_ids(label_ids=[label_id], limit=limit)
        return [self._get_metadata(mid) for mid in message_ids]

    def search_messages(
        self,
        query: str,
        label_name: str = "INBOX",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search messages with Gmail query syntax."""
        label_id = self._resolve_label_id(label_name)
        message_ids = self._list_message_ids(
            label_ids=[label_id], query=query, limit=limit,
        )
        return [self._get_metadata(mid) for mid in message_ids]

    def get_message(self, message_id: str) -> dict[str, Any]:
        """Fetch a full message with body and attachment metadata."""
        msg = (
            self._service.users().messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        payload = msg.get("payload", {})
        headers = _headers_dict(payload)
        return {
            "header": {
                "uid": msg["id"],
                "from_": headers.get("From", ""),
                "to": headers.get("To", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
            },
            "body_text": _extract_text_body(payload),
            "attachments": _list_attachments(msg["id"], payload),
        }

    def get_attachment(
        self, message_id: str, attachment_id: str,
    ) -> tuple[bytes, str, str]:
        """Download one attachment. Returns (bytes, filename, mime_type)."""
        resp = (
            self._service.users().messages().attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )
        data = base64.urlsafe_b64decode(resp["data"])
        filename, mime_type = self._find_attachment_meta(
            message_id, attachment_id,
        )
        return data, filename, mime_type

    def _find_attachment_meta(
        self, message_id: str, attachment_id: str,
    ) -> tuple[str, str]:
        """Look up filename and mime_type for an attachment ID."""
        msg = (
            self._service.users().messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        for part in _walk_parts(msg.get("payload", {})):
            body = part.get("body", {})
            if body.get("attachmentId") == attachment_id:
                return (
                    part.get("filename", ""),
                    part.get("mimeType", "application/octet-stream"),
                )
        return ("", "application/octet-stream")

    # --- write operations -----------------------------------------------------

    def send_message(
        self,
        to: list[str],
        subject: str,
        body: str,
        attachments: list[dict[str, str]] | None = None,
    ) -> str:
        """Send an email. Returns the Gmail message ID.

        Args:
            to: Recipient addresses.
            subject: Subject line.
            body: Plain-text body.
            attachments: Optional list of ``{filename, mime_type, data_b64}`` dicts.
        """
        if attachments:
            msg = email.mime.multipart.MIMEMultipart()
            msg.attach(email.mime.text.MIMEText(body, "plain"))
            for att in attachments:
                part = email.mime.base.MIMEBase(*att["mime_type"].split("/", 1))
                part.set_payload(base64.b64decode(att["data_b64"]))
                email.encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition", "attachment",
                    filename=att.get("filename", "attachment"),
                )
                msg.attach(part)
        else:
            msg = email.mime.text.MIMEText(body, "plain")

        msg["To"] = ", ".join(to)
        msg["Subject"] = subject

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        result = (
            self._service.users().messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )
        return result.get("id", "")

    def move_messages(
        self,
        folder: str,
        uids: list[str],
        dest_folder: str,
    ) -> None:
        """Move messages from one label to another.

        Translates the IMAP-style folder/move semantics into Gmail
        label add/remove operations.
        """
        remove_id = self._resolve_label_id(folder)
        add_id = self._resolve_label_id(dest_folder)
        for uid in uids:
            self._service.users().messages().modify(
                userId="me",
                id=uid,
                body={
                    "addLabelIds": [add_id],
                    "removeLabelIds": [remove_id],
                },
            ).execute()

    # --- internal helpers ----------------------------------------------------

    def _list_message_ids(
        self,
        *,
        label_ids: list[str] | None = None,
        query: str | None = None,
        limit: int = 20,
    ) -> list[str]:
        """Paginated message ID fetch."""
        results: list[str] = []
        page_token: str | None = None
        while len(results) < limit:
            page_size = min(limit - len(results), 100)
            kwargs: dict[str, Any] = {
                "userId": "me",
                "maxResults": page_size,
            }
            if label_ids:
                kwargs["labelIds"] = label_ids
            if query:
                kwargs["q"] = query
            if page_token:
                kwargs["pageToken"] = page_token

            resp = self._service.users().messages().list(**kwargs).execute()
            for m in resp.get("messages", []):
                results.append(m["id"])
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return results[:limit]

    def _get_metadata(self, message_id: str) -> dict[str, Any]:
        """Fetch just the envelope headers for one message."""
        msg = (
            self._service.users().messages()
            .get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"],
            )
            .execute()
        )
        headers = _headers_dict(msg.get("payload", {}))
        return {
            "uid": msg["id"],
            "from_": headers.get("From", ""),
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
        }


def _headers_dict(payload: dict[str, Any]) -> dict[str, str]:
    """Extract headers list into a name→value dict."""
    return {
        h["name"]: h["value"]
        for h in payload.get("headers", [])
        if "name" in h and "value" in h
    }


def _extract_text_body(payload: dict[str, Any]) -> str:
    """Best-effort plain-text body extraction from MIME parts."""
    mime = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")

    if mime == "text/plain" and body_data:
        return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        result = _extract_text_body(part)
        if result:
            return result
    return ""


def _list_attachments(
    message_id: str, payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Collect attachment metadata from MIME parts."""
    attachments: list[dict[str, Any]] = []
    for part in _walk_parts(payload):
        body = part.get("body", {})
        if body.get("attachmentId") and part.get("filename"):
            attachments.append({
                "id": body["attachmentId"],
                "filename": part.get("filename", ""),
                "mime_type": part.get("mimeType", "application/octet-stream"),
                "size": body.get("size", 0),
            })
    return attachments


def _walk_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the nested MIME part tree into a list."""
    parts: list[dict[str, Any]] = []
    for part in payload.get("parts", []):
        parts.append(part)
        parts.extend(_walk_parts(part))
    return parts
