"""Agent tool: list the folders (mailboxes) of a connected email integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)


async def list_email_folders(integration_id: str) -> str:
    """List the folders (mailboxes) available on a connected email integration.

    Args:
        integration_id: Identifier of the email integration to query.

    Returns:
        A plain-text message — either a bulleted folder list, a
        "not connected" notice, or an error description suitable to surface
        verbatim.
    """
    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "list_mailboxes",
            {},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationError as exc:
        logger.warning("list_email_folders(%r) failed: %s", integration_id, exc)
        return f"Failed to list folders for {integration_id!r}: {exc}"

    folders = [m["name"] for m in result.get("mailboxes", [])]
    if not folders:
        return f"No folders found on {integration_id!r}."
    joined = "\n".join(f"- {name}" for name in folders)
    return f"Folders on {integration_id!r}:\n{joined}"


def build_list_email_folders_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Return a turn-scoped tool whose docstring advertises the given IDs.

    The tool-to-JSON-schema converter reads `__doc__`, so embedding the current
    integration IDs in the description + arg-doc gives the model the exact
    set of valid `integration_id` values for this turn.
    """
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _list_email_folders(integration_id: str) -> str:
        return await list_email_folders(integration_id)

    _list_email_folders.__name__ = list_email_folders.__name__
    _list_email_folders.__doc__ = (
        "List the folders (mailboxes) available on a connected email "
        f"integration. Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        f"    integration_id: One of the registered email integration IDs: {ids_line}.\n\n"
        "Returns:\n"
        "    A plain-text message — either a bulleted folder list, a "
        '"not connected" notice, or an error description suitable to surface '
        "verbatim.\n"
    )
    return _list_email_folders
