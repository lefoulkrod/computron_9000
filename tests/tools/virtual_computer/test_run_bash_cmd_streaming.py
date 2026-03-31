"""Tests for run_bash_cmd streaming and thread-cleanup behaviour."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from tools.virtual_computer.run_bash_cmd import RunBashCmdError, run_bash_cmd


def _make_config(container_name: str = "computron") -> MagicMock:
    cfg = MagicMock()
    cfg.virtual_computer.container_name = container_name
    cfg.virtual_computer.container_user = "user"
    cfg.virtual_computer.container_working_dir = "/workspace"
    return cfg


def _make_podman_client(container_name: str = "computron") -> tuple[MagicMock, MagicMock]:
    """Return (mock_PodmanClient_class, mock_api_client)."""
    mock_container = MagicMock()
    mock_container.name = container_name

    mock_api_client = MagicMock()

    mock_client = MagicMock()
    mock_client.containers.list.return_value = [mock_container]
    mock_client.api = mock_api_client

    mock_podman_cls = MagicMock()
    mock_podman_cls.return_value.from_env.return_value = mock_client

    return mock_podman_cls, mock_api_client


@pytest.mark.unit
@pytest.mark.asyncio
async def test_timeout_closes_exec_response_to_unblock_thread() -> None:
    """Closing the exec response on timeout unblocks the stream thread promptly.

    The stream thread blocks in stream_frames() (simulated by waiting on an Event).
    The fix calls response.close() when the command times out; the mock close()
    sets the Event, allowing the thread to exit.  If close() is never called,
    thread_unblocked is never set and the assertion fails.
    """
    close_called = threading.Event()
    thread_unblocked = threading.Event()

    class _StuckResponse:
        def raise_for_status(self) -> None:
            pass

        def close(self) -> None:
            close_called.set()

    # Generator that blocks on blocking I/O until the response is closed.
    def _blocking_stream_frames(resp: object, demux: bool = False):  # noqa: ANN202
        close_called.wait(timeout=5.0)  # blocks the executor thread
        thread_unblocked.set()
        return
        yield  # pragma: no cover — makes this a generator function

    stuck_resp = _StuckResponse()

    def _api_post(path: str, **kwargs: object) -> MagicMock:
        if "start" in path:
            return stuck_resp
        # exec-create response
        resp = MagicMock()
        resp.json.return_value = {"Id": "fake-exec-id"}
        return resp

    mock_podman_cls, mock_api_client = _make_podman_client()
    mock_api_client.post.side_effect = _api_post

    with (
        patch("tools.virtual_computer.run_bash_cmd.PodmanClient", mock_podman_cls),
        patch("tools.virtual_computer.run_bash_cmd.stream_frames", side_effect=_blocking_stream_frames),
        patch("tools.virtual_computer.run_bash_cmd.publish_event"),
        patch("tools.virtual_computer.run_bash_cmd.load_config", return_value=_make_config()),
        patch("tools.virtual_computer.run_bash_cmd.get_current_workspace_folder", return_value=None),
    ):
        with pytest.raises(RunBashCmdError, match="Timeout"):
            await run_bash_cmd("sleep 999", timeout=0.05)

    # Thread must unblock promptly — response.close() should have been called.
    assert thread_unblocked.wait(timeout=2.0), (
        "stream thread did not exit after timeout: response.close() was not called"
    )
