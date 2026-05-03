"""Agent tool: full-text search across Google Drive."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client
from tools.integrations.drive._format import format_file

logger = logging.getLogger(__name__)


async def search_drive_files(
    integration_id: str,
    query: str,
    limit: int = 30,
) -> str:
    """Search for files in Google Drive by name or content.

    Args:
        integration_id: Identifier of the Google Workspace integration.
        query: Text to search for (matches file names and content).
        limit: Maximum results to return (1–100, default 30).

    Returns:
        Plain-text listing of matching files, or a short error/empty notice.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "search_drive_files",
            {"query": query, "limit": limit},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("search_drive_files(%r, %r) failed: %s", integration_id, query, exc)
        return f"Failed to search Drive: {exc}"

    files = result.get("files", [])
    if not files:
        return f"No files matching {query!r}."
    lines = [format_file(f) for f in files]
    return f"Drive search results for {query!r} ({len(lines)}):\n" + "\n".join(lines)


def build_search_drive_files_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _search_drive_files(
        integration_id: str,
        query: str,
        limit: int = 30,
    ) -> str:
        return await search_drive_files(integration_id, query, limit)

    _search_drive_files.__name__ = search_drive_files.__name__
    _search_drive_files.__doc__ = (
        "Search Google Drive using a Drive API query string. Trashed files "
        "are excluded automatically. Returns one file per line with the "
        f"file ID in brackets. Valid integration IDs: {ids_line}.\n\n"
        "Query syntax (Drive API q-string):\n"
        "    fullText contains 'budget'          — search file content and names\n"
        "    name contains 'report'              — match file name only\n"
        "    name = 'Q1 Report.pdf'              — exact file name\n"
        "    mimeType = 'application/pdf'        — filter by type\n"
        "    modifiedTime > '2026-01-01T00:00:00' — modified after date\n"
        "    'FOLDER_ID' in parents              — files in a specific folder\n"
        "    Combine with 'and', 'or', 'not'.\n"
        "    Common mimeTypes: application/pdf, application/vnd.google-apps.document,\n"
        "    application/vnd.google-apps.spreadsheet, application/vnd.google-apps.folder\n\n"
        "Args:\n"
        "    integration_id: Which integration to search.\n"
        "    query: Drive API q-string.\n"
        "    limit: Maximum results to return (1-100, default 30).\n\n"
        "Returns:\n"
        "    Plain text — one file per line, or a short empty/error notice.\n"
    )
    return _search_drive_files
