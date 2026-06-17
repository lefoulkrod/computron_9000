"""Unified agent tools for Drive integrations (Google Drive and iCloud Drive).

All tools take an opaque ``handle`` string. For Google Drive, handles are
``id:<file_id>`` and survive renames/moves. For rclone-backed remotes (iCloud
Drive), handles are POSIX-style paths from the remote root. ``drive_list``
returns the handle alongside each entry's name, so the agent never has to
know which format it's looking at.

Read tools (``drive_list``, ``drive_download``) require DRIVE read access;
the rest require DRIVE read+write. ``drive_share`` is Google-only and is
only registered on integrations whose broker supports it.
"""

from tools.integrations.drive.delete import build_drive_delete_tool, drive_delete
from tools.integrations.drive.download import build_drive_download_tool, drive_download
from tools.integrations.drive.list import build_drive_list_tool, drive_list
from tools.integrations.drive.mkdir import build_drive_mkdir_tool, drive_mkdir
from tools.integrations.drive.move import build_drive_move_tool, drive_move
from tools.integrations.drive.share import build_drive_share_tool, drive_share
from tools.integrations.drive.upload import build_drive_upload_tool, drive_upload

__all__ = [
    "build_drive_delete_tool",
    "build_drive_download_tool",
    "build_drive_list_tool",
    "build_drive_mkdir_tool",
    "build_drive_move_tool",
    "build_drive_share_tool",
    "build_drive_upload_tool",
    "drive_delete",
    "drive_download",
    "drive_list",
    "drive_mkdir",
    "drive_move",
    "drive_share",
    "drive_upload",
]
