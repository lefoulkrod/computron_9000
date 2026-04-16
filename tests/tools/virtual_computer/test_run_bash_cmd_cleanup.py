"""Tests for run_bash_cmd timeout, process-group kill, and cancellation behaviour.

These tests launch real bash subprocesses (no external network/service calls)
so they exercise the real OS-level process group and signal handling that
``run_bash_cmd`` relies on.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.virtual_computer.run_bash_cmd import (
    BASH_CMD_TIMEOUT,
    RunBashCmdError,
    run_bash_cmd,
)


def _make_config(home_dir: str = "/tmp") -> MagicMock:
    cfg = MagicMock()
    cfg.virtual_computer.home_dir = home_dir
    return cfg


def _patches(home_dir: str = "/tmp") -> contextlib.ExitStack:
    """Return a single context manager stacking the patches each test needs."""
    stack = contextlib.ExitStack()
    stack.enter_context(patch("tools.virtual_computer.run_bash_cmd.publish_event"))
    stack.enter_context(patch(
        "tools.virtual_computer.run_bash_cmd.load_config",
        return_value=_make_config(home_dir),
    ))
    return stack


def _pid_alive(pid: int) -> bool:
    """Return True if ``pid`` is still a live process (signal 0 probe)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists but owned by someone else — for our tests that still counts as alive.
        return True
    return True


def _read_pid(path: Path) -> int:
    """Poll for a pid file the shell wrote, then return its contents."""
    for _ in range(50):
        if path.exists():
            text = path.read_text().strip()
            if text:
                return int(text)
        time.sleep(0.05)
    raise AssertionError(f"pid file never appeared at {path}")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_timeout_kills_whole_process_tree(tmp_path: Path) -> None:
    """Timeout must SIGKILL the whole tree, not just the bash leader.

    Spawns bash → a detached ``sleep`` that writes its pid to a file and then
    sleeps for 60s. After the 0.3s timeout fires, the sleep process must be
    dead — proving the timeout path kills descendants, not just bash.
    """
    pid_file = tmp_path / "child.pid"
    # The inner sleep is launched synchronously but in the background.
    # Without start_new_session + killpg it would survive bash's SIGKILL.
    cmd = f"sleep 60 & echo $! > {pid_file}; wait"

    with _patches(str(tmp_path)), pytest.raises(RunBashCmdError, match="Timeout"):
        await run_bash_cmd(cmd, timeout=0.3)

    child_pid = _read_pid(pid_file)

    # Give the OS a moment to reap after SIGKILL on the group.
    for _ in range(20):
        if not _pid_alive(child_pid):
            break
        await asyncio.sleep(0.05)

    assert not _pid_alive(child_pid), (
        f"grandchild pid {child_pid} survived timeout — "
        "process-group kill not working"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_timeout_fires_when_streams_close_but_process_lives(
    tmp_path: Path,
) -> None:
    """Commands that close stdout/stderr but keep running must still time out.

    Reproduces the daemonizing-process foot-gun: bash closes fds 1 and 2 then
    sleeps. Before the fix, ``_read_stream`` hit EOF immediately, exited the
    ``wait_for``, and the bare ``proc.wait()`` afterwards hung without a
    timeout. With the fix, ``proc.wait()`` is inside the ``wait_for``, so the
    timeout fires regardless of stream state.
    """
    # Close stdout and stderr, then sleep 30s. Streams EOF immediately;
    # process keeps running. Must still hit the 0.5s timeout.
    cmd = "exec 1>&- 2>&-; sleep 30"

    with _patches(str(tmp_path)):
        start = asyncio.get_event_loop().time()
        with pytest.raises(RunBashCmdError, match="Timeout"):
            await run_bash_cmd(cmd, timeout=0.5)
        elapsed = asyncio.get_event_loop().time() - start

    # Should fire within a fraction of a second of the timeout, definitely
    # not wait 30s for the sleep to finish.
    assert elapsed < 5.0, (
        f"run_bash_cmd took {elapsed:.2f}s — timeout did not cover proc.wait()"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancellation_kills_subprocess_tree(tmp_path: Path) -> None:
    """Cancelling the task must kill the subprocess tree, not leak it.

    Before the fix, ``CancelledError`` bypassed the ``except TimeoutError``
    handler, so ``proc.kill()`` never ran and the subprocess survived.
    """
    pid_file = tmp_path / "child.pid"
    cmd = f"sleep 60 & echo $! > {pid_file}; wait"

    with _patches(str(tmp_path)):
        task = asyncio.create_task(run_bash_cmd(cmd, timeout=30.0))

        # Wait for the child to actually start and record its pid.
        for _ in range(50):
            if pid_file.exists() and pid_file.read_text().strip():
                break
            await asyncio.sleep(0.05)

        child_pid = _read_pid(pid_file)
        assert _pid_alive(child_pid), "child never started"

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    for _ in range(40):
        if not _pid_alive(child_pid):
            break
        await asyncio.sleep(0.05)

    assert not _pid_alive(child_pid), (
        f"grandchild pid {child_pid} survived task cancellation — "
        "finally-block cleanup not running"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_successful_command_returns_output(tmp_path: Path) -> None:
    """Sanity: a fast command still works end-to-end with the new plumbing."""
    with _patches(str(tmp_path)):
        result = await run_bash_cmd("echo hello && echo bye >&2", timeout=5.0)

    assert result.exit_code == 0
    assert result.stdout == "hello"
    assert result.stderr == "bye"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_backgrounded_command_returns_promptly(tmp_path: Path) -> None:
    """A backgrounded detached command must return without waiting for it.

    Ensures the ``& disown``-style pattern the prompt recommends still works —
    proc.wait() inside the timeout should still fire once bash exits.
    """
    log_file = tmp_path / "out.log"
    # Redirect output so the child doesn't keep bash's pipes open, and
    # background it. bash exits immediately; the sleep child lives on.
    cmd = f"nohup sleep 5 > {log_file} 2>&1 &"

    with _patches(str(tmp_path)):
        start = asyncio.get_event_loop().time()
        result = await run_bash_cmd(cmd, timeout=3.0)
        elapsed = asyncio.get_event_loop().time() - start

    assert result.exit_code == 0, f"backgrounded cmd got exit_code={result.exit_code}"
    assert elapsed < 2.0, f"backgrounded cmd took {elapsed:.2f}s — should return instantly"


@pytest.mark.unit
def test_default_timeout_constant_unchanged() -> None:
    """Guard rail: the default timeout constant is 120s.

    This is the ceiling applied when the agent doesn't pass an explicit
    timeout. Raising it silently lets runaway commands waste minutes of
    wall time; lowering it breaks legitimate commands like package
    installs. If you really need to change it, update this test.
    """
    assert BASH_CMD_TIMEOUT == 120.0


@pytest.mark.unit
def test_kill_process_group_tolerates_dead_pid() -> None:
    """``_kill_process_group`` must not raise if the process is already gone."""
    from tools.virtual_computer.run_bash_cmd import _kill_process_group

    # Fork a trivial child, wait for it to die, then try to signal its group.
    # pid recycling is unlikely in this window; the call just needs to not
    # crash on ProcessLookupError.
    proc = subprocess.Popen(["true"], start_new_session=True)
    proc.wait()
    _kill_process_group(proc.pid)


@pytest.mark.unit
def test_kill_process_group_uses_sigkill_on_group() -> None:
    """``_kill_process_group`` calls ``os.killpg`` with SIGKILL."""
    from tools.virtual_computer.run_bash_cmd import _kill_process_group

    with patch("tools.virtual_computer.run_bash_cmd.os.killpg") as mock_killpg:
        _kill_process_group(12345)
        mock_killpg.assert_called_once_with(12345, signal.SIGKILL)
