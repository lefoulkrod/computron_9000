"""Google Contacts read operations via the People API v1."""

from __future__ import annotations

import logging
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

_PERSON_FIELDS = "names,emailAddresses,phoneNumbers,organizations"


class ContactsClient:
    """Thin wrapper around the People API v1."""

    def __init__(self, creds: Credentials) -> None:
        self._creds = creds

    def _service(self):  # noqa: ANN202
        return build("people", "v1", credentials=self._creds, cache_discovery=False)

    def list_contacts(self, limit: int = 50) -> list[dict[str, Any]]:
        """List the user's contacts."""
        results: list[dict[str, Any]] = []
        page_token: str | None = None
        while len(results) < limit:
            page_size = min(limit - len(results), 100)
            resp = (
                self._service().people()
                .connections()
                .list(
                    resourceName="people/me",
                    personFields=_PERSON_FIELDS,
                    pageSize=page_size,
                    pageToken=page_token,
                    sortOrder="LAST_NAME_ASCENDING",
                )
                .execute()
            )
            results.extend(resp.get("connections", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return results[:limit]

    def search_contacts(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search the user's contacts by name, email, or phone."""
        resp = (
            self._service().people()
            .searchContacts(
                query=query,
                readMask=_PERSON_FIELDS,
                pageSize=min(limit, 30),
            )
            .execute()
        )
        return [r["person"] for r in resp.get("results", []) if "person" in r]
