"""Tests for run_bash_cmd timeout behaviour."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.virtual_computer.run_bash_cmd import RunBashCmdError, run_bash_cmd


def _make_config(home_dir: str = "/tmp") -> MagicMock:
    cfg = MagicMock()
    cfg.virtual_computer.home_dir = home_dir
    return cfg


@pytest.mark.unit
@pytest.mark.asyncio
async def test_timeout_kills_process() -> None:
    """A command that exceeds the timeout should raise RunBashCmdError.

    The subprocess is mocked to hang forever; the timeout logic in run_bash_cmd
    should kill it and raise.
    """
    mock_proc = AsyncMock()
    mock_proc.returncode = -9
    mock_proc.stdout = AsyncMock()
    mock_proc.stderr = AsyncMock()

    # Make the streams hang so the timeout fires
    async def _hang_read(_n: int = -1) -> bytes:
        await asyncio.sleep(999)
        return b""  # pragma: no cover

    mock_proc.stdout.read = _hang_read
    mock_proc.stderr.read = _hang_read
    mock_proc.kill = MagicMock()
    mock_proc.wait = AsyncMock()

    async def _create_subprocess_shell(*args, **kwargs):
        return mock_proc

    with (
        patch("tools.virtual_computer.run_bash_cmd.asyncio.create_subprocess_shell",
              side_effect=_create_subprocess_shell),
        patch("tools.virtual_computer.run_bash_cmd.publish_event"),
        patch("tools.virtual_computer.run_bash_cmd.load_config",
              return_value=_make_config()),
    ):
        with pytest.raises(RunBashCmdError, match="Timeout"):
            await run_bash_cmd("sleep 999", timeout=0.05)
