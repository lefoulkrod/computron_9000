"""Agent tool: share a Google Drive file with others."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from config import load_config
from integrations import broker_client

logger = logging.getLogger(__name__)

_VALID_ROLES = ("reader", "commenter", "writer")
_VALID_TYPES = ("user", "group", "domain", "anyone")


async def share_drive_file(
    integration_id: str,
    file_id: str,
    role: str,
    share_type: str = "user",
    email: str | None = None,
) -> str:
    """Share a Drive file by creating a permission.

    Args:
        integration_id: Identifier of the Google Workspace integration.
        file_id: Drive file ID to share.
        role: Access level — ``"reader"``, ``"commenter"``, or ``"writer"``.
        share_type: Who to share with — ``"user"``, ``"group"``, ``"domain"``,
            or ``"anyone"`` (for link sharing).
        email: Email address of the user or group. Required when
            share_type is ``"user"`` or ``"group"``.

    Returns:
        Plain text — a confirmation, or a short error notice.
    """
    if role not in _VALID_ROLES:
        return f"Invalid role {role!r} — must be one of: {', '.join(_VALID_ROLES)}."
    if share_type not in _VALID_TYPES:
        return f"Invalid type {share_type!r} — must be one of: {', '.join(_VALID_TYPES)}."
    if share_type in ("user", "group") and not email:
        return f"'email' is required when sharing with a {share_type}."

    app_sock = load_config().integrations.app_sock_path
    try:
        result = await broker_client.call(
            integration_id,
            "share_drive_file",
            {
                "file_id": file_id,
                "role": role,
                "type": share_type,
                "email": email,
            },
            app_sock_path=app_sock,
        )
    except broker_client.IntegrationNotConnected:
        return f"Integration {integration_id!r} is not connected."
    except broker_client.IntegrationWriteDenied:
        return f"Writes are disabled for {integration_id!r}."
    except broker_client.IntegrationError as exc:
        logger.warning(
            "share_drive_file(%r, %r) failed: %s", integration_id, file_id, exc,
        )
        return f"Failed to share file via {integration_id!r}: {exc}"

    perm = result.get("permission", {})
    if share_type == "anyone":
        return f"Shared file {file_id} with anyone as {role}."
    target = perm.get("emailAddress", email or share_type)
    return f"Shared file {file_id} with {target} as {role}."


def build_share_drive_file_tool(integration_ids: Iterable[str]) -> Callable[..., Any]:
    """Turn-scoped wrapper whose docstring advertises the current IDs."""
    ids = sorted(integration_ids)
    ids_line = ", ".join(repr(i) for i in ids) if ids else "(none registered)"

    async def _share_drive_file(
        integration_id: str,
        file_id: str,
        role: str,
        share_type: str = "user",
        email: str | None = None,
    ) -> str:
        return await share_drive_file(
            integration_id, file_id, role, share_type, email,
        )

    _share_drive_file.__name__ = share_drive_file.__name__
    _share_drive_file.__doc__ = (
        "Share a Google Drive file by creating a permission. Use "
        'share_type="anyone" for link sharing (no email needed), or '
        'share_type="user" with an email to share with a specific person. '
        f"Valid integration IDs: {ids_line}.\n\n"
        "Args:\n"
        "    integration_id: Which integration to use.\n"
        "    file_id: Drive file ID to share.\n"
        '    role: "reader", "commenter", or "writer".\n'
        '    share_type: "user", "group", "domain", or "anyone" (default "user").\n'
        "    email: Required for user/group sharing.\n\n"
        "Returns:\n"
        "    Plain text — a confirmation, or an error notice.\n"
    )
    return _share_drive_file
