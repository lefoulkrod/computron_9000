"""Unit tests for desktop lifecycle management."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.desktop._exec import DesktopExecError
from tools.desktop import _lifecycle
from tools.desktop._lifecycle import ensure_desktop_running, is_desktop_running


@pytest.mark.unit
@pytest.mark.asyncio
async def test_is_desktop_running_true():
    """is_desktop_running() returns True when Xvfb and x11vnc are running."""
    with patch(
        "tools.desktop._lifecycle._run_desktop_cmd",
        new_callable=AsyncMock,
        return_value="ok\n",
    ):
        assert await is_desktop_running() is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_is_desktop_running_false():
    """is_desktop_running() returns False when Xvfb is not running."""
    with patch(
        "tools.desktop._lifecycle._run_desktop_cmd",
        new_callable=AsyncMock,
        return_value="",
    ):
        assert await is_desktop_running() is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_is_desktop_running_on_error():
    """is_desktop_running() returns False on DesktopExecError."""
    with patch(
        "tools.desktop._lifecycle._run_desktop_cmd",
        new_callable=AsyncMock,
        side_effect=DesktopExecError("no container"),
    ):
        assert await is_desktop_running() is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_desktop_running_already_running():
    """ensure_desktop_running() emits event and skips start when already up."""
    _lifecycle._ui_notified = False
    mock_cfg = MagicMock()
    mock_cfg.desktop.resolution = "1280x720"
    with (
        patch(
            "tools.desktop._lifecycle.is_desktop_running",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_check,
        patch("tools.desktop._lifecycle.publish_event") as mock_publish,
        patch("tools.desktop._lifecycle.load_config", return_value=mock_cfg),
    ):
        await ensure_desktop_running()
        mock_check.assert_awaited_once()
        # Should still emit the UI event
        mock_publish.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_desktop_running_waits_and_polls():
    """ensure_desktop_running() polls until desktop is ready, then emits event."""
    _lifecycle._ui_notified = False
    mock_cfg = MagicMock()
    mock_cfg.desktop.resolution = "1280x720"

    # First call returns False, second returns True (simulates startup delay)
    with (
        patch(
            "tools.desktop._lifecycle.is_desktop_running",
            new_callable=AsyncMock,
            side_effect=[False, False, True],
        ),
        patch("tools.desktop._lifecycle.load_config", return_value=mock_cfg),
        patch("tools.desktop._lifecycle.publish_event") as mock_publish,
        patch("tools.desktop._lifecycle.asyncio.sleep", new_callable=AsyncMock),
    ):
        await ensure_desktop_running()
        mock_publish.assert_called_once()
        event = mock_publish.call_args[0][0]
        assert event.event.type == "desktop_active"
        assert event.event.resolution == "1280x720"
