"""Agent tool: share a file or folder by email (Google Drive only)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)

_VALID_ROLES = {"reader", "commenter", "writer"}


async def drive_share(
    integration_id: str,
    handle: str,
    email: str,
    role: str = "reader",
) -> str:
    """Grant another email address access to a file or folder.

    Only available on Google Drive integrations — path-addressed remotes
    (iCloud Drive via rclone) don't expose a sharing API, and the tool is not
    registered for those.

    Args:
        integration_id: Which Google Drive integration to use.
        handle: Handle of the entry to share.
        email: Email address to grant access to.
        role: ``"reader"`` (default), ``"commenter"``, or ``"writer"``.

    Returns:
        Plain text — share confirmation.
    """
    if role not in _VALID_ROLES:
        return f"role must be one of {sorted(_VALID_ROLES)} (got {role!r})."
    app_sock = load_config().integrations.app_sock_path
    try:
        await broker_client.call(
            integration_id, "drive_share",
            {"handle": handle, "email": email, "role": role, "type": "user"},
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationPermissionDenied:
        return f"Writing is disabled for {integration_id!r}. Enable read+write access in Settings."
    except broker_client.IntegrationError as exc:
        logger.warning("drive_share(%r, %r, %r) failed: %s", integration_id, handle, email, exc)
        return f"Failed to share {handle!r}: {exc}"
    return f"Shared {handle!r} with {email} as {role}."


def build_drive_share_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _drive_share(
        integration_id: str, handle: str, email: str, role: str = "reader",
    ) -> str:
        return await drive_share(integration_id, handle, email, role)

    _drive_share.__name__ = drive_share.__name__
    _drive_share.__doc__ = (
        "Grant another email address access to a Google Drive file or folder. "
        "Google Drive only. "
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which Google Drive integration to use.\n"
        "    handle: Handle of the entry to share.\n"
        "    email: Email address to grant access to.\n"
        '    role: "reader" (default), "commenter", or "writer".\n\n'
        "Returns:\n"
        "    Plain text — share confirmation.\n"
    )
    return _drive_share
