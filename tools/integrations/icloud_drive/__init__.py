"""Agent tools for iCloud Drive integrations (rclone-backed storage).

Each ``build_*_tool`` returns a turn-scoped callable whose docstring lists the
currently-registered integration IDs. Read tools are gated on DRIVE read
access; write tools (upload, move, delete, mkdir) on DRIVE read+write.
"""

from tools.integrations.icloud_drive.about import build_icloud_drive_about_tool
from tools.integrations.icloud_drive.delete import build_icloud_drive_delete_tool
from tools.integrations.icloud_drive.download import build_icloud_drive_download_tool
from tools.integrations.icloud_drive.list_directory import build_icloud_drive_list_directory_tool
from tools.integrations.icloud_drive.mkdir import build_icloud_drive_mkdir_tool
from tools.integrations.icloud_drive.move import build_icloud_drive_move_tool
from tools.integrations.icloud_drive.read_file import build_icloud_drive_read_file_tool
from tools.integrations.icloud_drive.search import build_icloud_drive_search_tool
from tools.integrations.icloud_drive.size import build_icloud_drive_size_tool
from tools.integrations.icloud_drive.upload import build_icloud_drive_upload_tool

__all__ = [
    "build_icloud_drive_about_tool",
    "build_icloud_drive_delete_tool",
    "build_icloud_drive_download_tool",
    "build_icloud_drive_list_directory_tool",
    "build_icloud_drive_mkdir_tool",
    "build_icloud_drive_move_tool",
    "build_icloud_drive_read_file_tool",
    "build_icloud_drive_search_tool",
    "build_icloud_drive_size_tool",
    "build_icloud_drive_upload_tool",
]
