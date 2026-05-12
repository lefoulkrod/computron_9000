"""Tests for ``sdk.tools._core.get_core_tools``.

Verifies that integration tools are gated correctly on per-capability
permissions: each capability/access combination should include exactly
the expected tool builders, and no tools should leak when an integration
is broken or has a capability set to OFF.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest

from integrations.permissions import Access, Capability, Permissions


@dataclass(frozen=True)
class _FakeRecord:
    """Minimal stand-in for ``RegisteredIntegration``."""

    id: str
    slug: str
    permissions: Permissions = field(default_factory=dict)
    state: str = "running"


def _tool_names(tools: list[Callable[..., Any]]) -> set[str]:
    return {t.__name__ for t in tools}


_ALWAYS_PRESENT = {
    "save_to_scratchpad",
    "recall_from_scratchpad",
    "load_skill",
    "list_available_skills",
    "list_agent_profiles",
    "spawn_agent",
    "send_file",
    "play_audio",
    "describe_image",
}

_EMAIL_READ_TOOLS = {
    "list_email_folders",
    "list_email_messages",
    "read_email_message",
    "search_email",
    "download_email_attachment",
}

_EMAIL_WRITE_TOOLS = {
    "send_email",
    "move_email",
}

_CALENDAR_READ_TOOLS = {
    "list_calendars",
    "list_events",
}

_CALENDAR_WRITE_TOOLS = {
    "create_event",
    "update_event",
    "delete_event",
}

_DRIVE_READ_TOOLS = {
    "list_drive_files",
    "search_drive_files",
    "get_drive_file_metadata",
    "export_drive_file",
}

_DRIVE_WRITE_TOOLS = {
    "upload_drive_file",
    "create_drive_folder",
    "update_drive_file",
    "trash_drive_file",
    "share_drive_file",
}

_CONTACTS_READ_TOOLS = {
    "list_contacts",
    "search_contacts",
}


@pytest.fixture(autouse=True)
def _stub_config(monkeypatch: pytest.MonkeyPatch) -> None:
    @dataclass
    class _Features:
        custom_tools: bool = False

    @dataclass
    class _Config:
        features: _Features = field(default_factory=_Features)

    monkeypatch.setattr("config.load_config", lambda: _Config())


def _stub_integrations(
    monkeypatch: pytest.MonkeyPatch,
    records: dict[str, _FakeRecord],
) -> None:
    monkeypatch.setattr(
        "tools.integrations.registered_integrations",
        AsyncMock(return_value=records),
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_no_integrations_returns_base_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no integrations registered, only the always-present tools appear."""
    _stub_integrations(monkeypatch, {})
    from sdk.tools._core import get_core_tools

    tools = await get_core_tools()
    names = _tool_names(tools)
    assert _ALWAYS_PRESENT <= names
    assert not names & (
        _EMAIL_READ_TOOLS | _EMAIL_WRITE_TOOLS | _CALENDAR_READ_TOOLS
        | _DRIVE_READ_TOOLS | _CONTACTS_READ_TOOLS
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_email_read_only_includes_read_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An integration with email:r gets read tools but not write tools."""
    _stub_integrations(monkeypatch, {
        "icloud_personal": _FakeRecord(
            id="icloud_personal",
            slug="icloud",
            permissions={Capability.EMAIL: Access.READ},
        ),
    })
    from sdk.tools._core import get_core_tools

    names = _tool_names(await get_core_tools())
    assert _EMAIL_READ_TOOLS <= names
    assert not names & _EMAIL_WRITE_TOOLS


@pytest.mark.asyncio
@pytest.mark.unit
async def test_email_read_write_includes_all_email_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An integration with email:rw gets both read and write tools."""
    _stub_integrations(monkeypatch, {
        "icloud_personal": _FakeRecord(
            id="icloud_personal",
            slug="icloud",
            permissions={Capability.EMAIL: Access.READ_WRITE},
        ),
    })
    from sdk.tools._core import get_core_tools

    names = _tool_names(await get_core_tools())
    assert (_EMAIL_READ_TOOLS | _EMAIL_WRITE_TOOLS) <= names


@pytest.mark.asyncio
@pytest.mark.unit
async def test_calendar_read_includes_calendar_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_integrations(monkeypatch, {
        "gw_work": _FakeRecord(
            id="gw_work",
            slug="google_workspace",
            permissions={Capability.CALENDAR: Access.READ},
        ),
    })
    from sdk.tools._core import get_core_tools

    names = _tool_names(await get_core_tools())
    assert _CALENDAR_READ_TOOLS <= names
    assert not names & _CALENDAR_WRITE_TOOLS
    assert not names & _EMAIL_READ_TOOLS


@pytest.mark.asyncio
@pytest.mark.unit
async def test_calendar_read_write_includes_all_calendar_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An integration with calendar:rw gets both read and write tools."""
    _stub_integrations(monkeypatch, {
        "gw_work": _FakeRecord(
            id="gw_work",
            slug="google_workspace",
            permissions={Capability.CALENDAR: Access.READ_WRITE},
        ),
    })
    from sdk.tools._core import get_core_tools

    names = _tool_names(await get_core_tools())
    assert (_CALENDAR_READ_TOOLS | _CALENDAR_WRITE_TOOLS) <= names


@pytest.mark.asyncio
@pytest.mark.unit
async def test_drive_read_includes_drive_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_integrations(monkeypatch, {
        "gw_work": _FakeRecord(
            id="gw_work",
            slug="google_workspace",
            permissions={Capability.DRIVE: Access.READ},
        ),
    })
    from sdk.tools._core import get_core_tools

    names = _tool_names(await get_core_tools())
    assert _DRIVE_READ_TOOLS <= names
    assert not names & (_EMAIL_READ_TOOLS | _CALENDAR_READ_TOOLS | _CONTACTS_READ_TOOLS)
    assert not names & _DRIVE_WRITE_TOOLS


@pytest.mark.asyncio
@pytest.mark.unit
async def test_drive_read_write_includes_all_drive_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An integration with drive:rw gets both read and write tools."""
    _stub_integrations(monkeypatch, {
        "gw_work": _FakeRecord(
            id="gw_work",
            slug="google_workspace",
            permissions={Capability.DRIVE: Access.READ_WRITE},
        ),
    })
    from sdk.tools._core import get_core_tools

    names = _tool_names(await get_core_tools())
    assert (_DRIVE_READ_TOOLS | _DRIVE_WRITE_TOOLS) <= names


@pytest.mark.asyncio
@pytest.mark.unit
async def test_contacts_read_includes_contacts_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_integrations(monkeypatch, {
        "gw_work": _FakeRecord(
            id="gw_work",
            slug="google_workspace",
            permissions={Capability.CONTACTS: Access.READ},
        ),
    })
    from sdk.tools._core import get_core_tools

    names = _tool_names(await get_core_tools())
    assert _CONTACTS_READ_TOOLS <= names
    assert not names & (_EMAIL_READ_TOOLS | _DRIVE_READ_TOOLS)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_broken_integration_excluded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Integrations not in 'running' state should not contribute tools."""
    _stub_integrations(monkeypatch, {
        "icloud_personal": _FakeRecord(
            id="icloud_personal",
            slug="icloud",
            permissions={Capability.EMAIL: Access.READ_WRITE},
            state="broken",
        ),
    })
    from sdk.tools._core import get_core_tools

    names = _tool_names(await get_core_tools())
    assert not names & (_EMAIL_READ_TOOLS | _EMAIL_WRITE_TOOLS)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_auth_failed_integration_excluded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_integrations(monkeypatch, {
        "icloud_personal": _FakeRecord(
            id="icloud_personal",
            slug="icloud",
            permissions={Capability.EMAIL: Access.READ_WRITE},
            state="auth_failed",
        ),
    })
    from sdk.tools._core import get_core_tools

    names = _tool_names(await get_core_tools())
    assert not names & (_EMAIL_READ_TOOLS | _EMAIL_WRITE_TOOLS)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_full_workspace_integration_includes_all_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Google Workspace integration with all capabilities enabled gets
    every integration tool."""
    _stub_integrations(monkeypatch, {
        "gw_work": _FakeRecord(
            id="gw_work",
            slug="google_workspace",
            permissions={
                Capability.EMAIL: Access.READ_WRITE,
                Capability.CALENDAR: Access.READ_WRITE,
                Capability.DRIVE: Access.READ_WRITE,
                Capability.CONTACTS: Access.READ,
            },
        ),
    })
    from sdk.tools._core import get_core_tools

    names = _tool_names(await get_core_tools())
    all_integration_tools = (
        _EMAIL_READ_TOOLS | _EMAIL_WRITE_TOOLS
        | _CALENDAR_READ_TOOLS | _CALENDAR_WRITE_TOOLS
        | _DRIVE_READ_TOOLS | _DRIVE_WRITE_TOOLS | _CONTACTS_READ_TOOLS
    )
    assert all_integration_tools <= names


@pytest.mark.asyncio
@pytest.mark.unit
async def test_off_capability_excluded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A capability set to OFF should not contribute its tools."""
    _stub_integrations(monkeypatch, {
        "gw_work": _FakeRecord(
            id="gw_work",
            slug="google_workspace",
            permissions={
                Capability.EMAIL: Access.READ,
                Capability.CALENDAR: Access.OFF,
            },
        ),
    })
    from sdk.tools._core import get_core_tools

    names = _tool_names(await get_core_tools())
    assert _EMAIL_READ_TOOLS <= names
    assert not names & _CALENDAR_READ_TOOLS


_ICLOUD_DRIVE_READ_TOOLS = {
    "icloud_drive_list_directory",
    "icloud_drive_search",
    "icloud_drive_size",
    "icloud_drive_about",
    "icloud_drive_read_file",
    "icloud_drive_download",
}

_ICLOUD_DRIVE_WRITE_TOOLS = {
    "icloud_drive_upload",
    "icloud_drive_move",
    "icloud_drive_delete",
    "icloud_drive_mkdir",
}


@pytest.mark.asyncio
@pytest.mark.unit
async def test_icloud_drive_read_includes_storage_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """drive:r on an icloud_drive integration gets the rclone read tools only."""
    _stub_integrations(monkeypatch, {
        "icloud_drive_me": _FakeRecord(
            id="icloud_drive_me",
            slug="icloud_drive",
            permissions={Capability.DRIVE: Access.READ},
        ),
    })
    from sdk.tools._core import get_core_tools

    names = _tool_names(await get_core_tools())
    assert _ICLOUD_DRIVE_READ_TOOLS <= names
    assert not names & _ICLOUD_DRIVE_WRITE_TOOLS
    # The Google Drive API tools must not leak onto an iCloud Drive integration.
    assert not names & (_DRIVE_READ_TOOLS | _DRIVE_WRITE_TOOLS)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_icloud_drive_read_write_includes_all_storage_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_integrations(monkeypatch, {
        "icloud_drive_me": _FakeRecord(
            id="icloud_drive_me",
            slug="icloud_drive",
            permissions={Capability.DRIVE: Access.READ_WRITE},
        ),
    })
    from sdk.tools._core import get_core_tools

    names = _tool_names(await get_core_tools())
    assert (_ICLOUD_DRIVE_READ_TOOLS | _ICLOUD_DRIVE_WRITE_TOOLS) <= names
    assert not names & (_DRIVE_READ_TOOLS | _DRIVE_WRITE_TOOLS)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_google_workspace_drive_does_not_get_storage_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A google_workspace integration with drive:rw gets Drive-API tools, not rclone ones."""
    _stub_integrations(monkeypatch, {
        "gw_work": _FakeRecord(
            id="gw_work",
            slug="google_workspace",
            permissions={Capability.DRIVE: Access.READ_WRITE},
        ),
    })
    from sdk.tools._core import get_core_tools

    names = _tool_names(await get_core_tools())
    assert (_DRIVE_READ_TOOLS | _DRIVE_WRITE_TOOLS) <= names
    assert not names & (_ICLOUD_DRIVE_READ_TOOLS | _ICLOUD_DRIVE_WRITE_TOOLS)
