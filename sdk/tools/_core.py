"""Core tools included in every agent's tool set."""

from collections.abc import Callable
from typing import Any

from integrations.permissions import Access, Capability


def _ids_with_access(
    records: dict[str, Any],
    cap: Capability,
    min_access: Access,
) -> frozenset[str]:
    """Return integration IDs whose permission for ``cap`` meets ``min_access``."""
    return frozenset(
        i for i, rec in records.items()
        if rec.state == "running"
        and rec.permissions.get(cap, Access.OFF) >= min_access
    )


async def get_core_tools() -> list[Callable[..., Any]]:
    """Return tools that every agent gets regardless of skill configuration.

    Async because the integration tool gating awaits the integrations cache,
    which loads lazily on first use after app startup.

    Lazy imports to avoid circular dependencies.
    """
    from config import load_config
    from sdk.skills._tools import list_available_skills, load_skill
    from agents._list_profiles_tool import list_agent_profiles
    from sdk.tools._spawn_agent import spawn_agent
    from tools.scratchpad import recall_from_scratchpad, save_to_scratchpad
    from tools.virtual_computer.describe_image import describe_image
    from tools.virtual_computer.file_output import send_file
    from tools.virtual_computer.play_audio import play_audio

    tools = [
        save_to_scratchpad,
        recall_from_scratchpad,
        load_skill,
        list_available_skills,
        list_agent_profiles,
        spawn_agent,
        send_file,
        play_audio,
        describe_image,
    ]
    if load_config().features.custom_tools:
        from tools.custom_tools import create_custom_tool, lookup_custom_tools, run_custom_tool
        tools.extend([create_custom_tool, lookup_custom_tools, run_custom_tool])

    from tools.integrations import registered_integrations
    records = await registered_integrations()

    email_ids = _ids_with_access(records, Capability.EMAIL, Access.READ)
    if email_ids:
        from tools.integrations.download_email_attachment import build_download_email_attachment_tool
        from tools.integrations.list_email_folders import build_list_email_folders_tool
        from tools.integrations.list_email_messages import build_list_email_messages_tool
        from tools.integrations.read_email_message import build_read_email_message_tool
        from tools.integrations.search_email import build_search_email_tool
        tools.append(build_list_email_folders_tool(email_ids))
        tools.append(build_list_email_messages_tool(email_ids))
        tools.append(build_read_email_message_tool(email_ids))
        tools.append(build_search_email_tool(email_ids))
        tools.append(build_download_email_attachment_tool(email_ids))

    email_write_ids = _ids_with_access(records, Capability.EMAIL, Access.READ_WRITE)
    if email_write_ids:
        from tools.integrations.move_email import build_move_email_tool
        from tools.integrations.send_email import build_send_email_tool
        tools.append(build_move_email_tool(email_write_ids))
        tools.append(build_send_email_tool(email_write_ids))

    calendar_ids = _ids_with_access(records, Capability.CALENDAR, Access.READ)
    if calendar_ids:
        from tools.integrations.list_calendars import build_list_calendars_tool
        from tools.integrations.list_events import build_list_events_tool
        tools.append(build_list_calendars_tool(calendar_ids))
        tools.append(build_list_events_tool(calendar_ids))

    calendar_write_ids = _ids_with_access(records, Capability.CALENDAR, Access.READ_WRITE)
    if calendar_write_ids:
        from tools.integrations.create_event import build_create_event_tool
        from tools.integrations.delete_event import build_delete_event_tool
        from tools.integrations.update_event import build_update_event_tool
        tools.append(build_create_event_tool(calendar_write_ids))
        tools.append(build_update_event_tool(calendar_write_ids))
        tools.append(build_delete_event_tool(calendar_write_ids))

    drive_ids = _ids_with_access(records, Capability.DRIVE, Access.READ)
    drive_write_ids = _ids_with_access(records, Capability.DRIVE, Access.READ_WRITE)

    # Two providers expose DRIVE today and their tool sets don't overlap yet:
    # Google Workspace uses the Drive-API tools (opaque file IDs, exports,
    # sharing); iCloud Drive uses the rclone-backed tools (POSIX-style paths).
    # Until the vocabularies are unified, registration is split by slug.
    gdrive_ids = frozenset(i for i in drive_ids if records[i].slug == "google_workspace")
    if gdrive_ids:
        from tools.integrations.drive.export_file import build_export_drive_file_tool
        from tools.integrations.drive.get_file_metadata import build_get_drive_file_metadata_tool
        from tools.integrations.drive.list_files import build_list_drive_files_tool
        from tools.integrations.drive.search_files import build_search_drive_files_tool
        tools.append(build_list_drive_files_tool(gdrive_ids))
        tools.append(build_search_drive_files_tool(gdrive_ids))
        tools.append(build_get_drive_file_metadata_tool(gdrive_ids))
        tools.append(build_export_drive_file_tool(gdrive_ids))

    gdrive_write_ids = frozenset(i for i in drive_write_ids if records[i].slug == "google_workspace")
    if gdrive_write_ids:
        from tools.integrations.drive.create_folder import build_create_drive_folder_tool
        from tools.integrations.drive.share_file import build_share_drive_file_tool
        from tools.integrations.drive.trash_file import build_trash_drive_file_tool
        from tools.integrations.drive.update_file import build_update_drive_file_tool
        from tools.integrations.drive.upload_file import build_upload_drive_file_tool
        tools.append(build_upload_drive_file_tool(gdrive_write_ids))
        tools.append(build_create_drive_folder_tool(gdrive_write_ids))
        tools.append(build_update_drive_file_tool(gdrive_write_ids))
        tools.append(build_trash_drive_file_tool(gdrive_write_ids))
        tools.append(build_share_drive_file_tool(gdrive_write_ids))

    icloud_drive_ids = frozenset(i for i in drive_ids if records[i].slug == "icloud_drive")
    if icloud_drive_ids:
        from tools.integrations.icloud_drive import (
            build_icloud_drive_about_tool,
            build_icloud_drive_download_tool,
            build_icloud_drive_list_directory_tool,
            build_icloud_drive_read_file_tool,
            build_icloud_drive_search_tool,
            build_icloud_drive_size_tool,
        )
        tools.append(build_icloud_drive_list_directory_tool(icloud_drive_ids))
        tools.append(build_icloud_drive_search_tool(icloud_drive_ids))
        tools.append(build_icloud_drive_size_tool(icloud_drive_ids))
        tools.append(build_icloud_drive_about_tool(icloud_drive_ids))
        tools.append(build_icloud_drive_read_file_tool(icloud_drive_ids))
        tools.append(build_icloud_drive_download_tool(icloud_drive_ids))

    icloud_drive_write_ids = frozenset(i for i in drive_write_ids if records[i].slug == "icloud_drive")
    if icloud_drive_write_ids:
        from tools.integrations.icloud_drive import (
            build_icloud_drive_delete_tool,
            build_icloud_drive_mkdir_tool,
            build_icloud_drive_move_tool,
            build_icloud_drive_upload_tool,
        )
        tools.append(build_icloud_drive_upload_tool(icloud_drive_write_ids))
        tools.append(build_icloud_drive_move_tool(icloud_drive_write_ids))
        tools.append(build_icloud_drive_delete_tool(icloud_drive_write_ids))
        tools.append(build_icloud_drive_mkdir_tool(icloud_drive_write_ids))

    contacts_ids = _ids_with_access(records, Capability.CONTACTS, Access.READ)
    if contacts_ids:
        from tools.integrations.contacts.list_contacts import build_list_contacts_tool
        from tools.integrations.contacts.search_contacts import build_search_contacts_tool
        tools.append(build_list_contacts_tool(contacts_ids))
        tools.append(build_search_contacts_tool(contacts_ids))

    return tools
