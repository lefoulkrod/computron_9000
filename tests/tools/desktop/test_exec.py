"""Unit tests for desktop exec helpers."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.desktop._exec import DesktopExecError, _run_desktop_cmd


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_desktop_cmd_timeout():
    """_run_desktop_cmd raises DesktopExecError when the command times out."""
    mock_proc = AsyncMock()
    mock_proc.returncode = None

    # communicate() hangs forever to trigger timeout
    async def _hang():
        await asyncio.sleep(999)
        return b"", b""  # pragma: no cover

    mock_proc.communicate = _hang

    async def _create_subprocess(*args, **kwargs):
        return mock_proc

    mock_cfg = MagicMock()
    mock_cfg.desktop.user_display = ":1"

    with (
        patch("tools.desktop._exec.load_config", return_value=mock_cfg),
        patch("asyncio.create_subprocess_shell", side_effect=_create_subprocess),
    ):
        with pytest.raises(DesktopExecError, match="timed out"):
            await _run_desktop_cmd("sleep 999", timeout=0.01)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_desktop_cmd_success():
    """_run_desktop_cmd returns stdout+stderr on success."""
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"hello", b""))

    async def _create_subprocess(*args, **kwargs):
        return mock_proc

    mock_cfg = MagicMock()
    mock_cfg.desktop.user_display = ":1"

    with (
        patch("tools.desktop._exec.load_config", return_value=mock_cfg),
        patch("asyncio.create_subprocess_shell", side_effect=_create_subprocess),
    ):
        result = await _run_desktop_cmd("echo hello")
        assert "hello" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_desktop_cmd_failure():
    """_run_desktop_cmd returns output even on non-zero exit."""
    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"error msg"))

    async def _create_subprocess(*args, **kwargs):
        return mock_proc

    mock_cfg = MagicMock()
    mock_cfg.desktop.user_display = ":1"

    with (
        patch("tools.desktop._exec.load_config", return_value=mock_cfg),
        patch("asyncio.create_subprocess_shell", side_effect=_create_subprocess),
    ):
        result = await _run_desktop_cmd("false")
        assert "error msg" in result
