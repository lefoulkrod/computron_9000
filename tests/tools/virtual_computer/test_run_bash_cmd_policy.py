"""Policy tests for run_bash_cmd allow/deny and timeouts."""

from __future__ import annotations

import importlib
import pytest

from tools.virtual_computer.run_bash_cmd import run_bash_cmd


@pytest.mark.asyncio
@pytest.mark.unit
async def test_denylist_blocks_http_server() -> None:
    """http.server should be blocked by denylist and return exit code 126."""
    res = await run_bash_cmd("python -m http.server 8000")
    assert res.exit_code == 126
    assert res.stderr is not None and "not allowed" in res.stderr.lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_allowlist_allows_echo(monkeypatch: pytest.MonkeyPatch) -> None:
    """A harmless echo command should be allowed and succeed (unit, mocked)."""

    # Mock config loader to avoid reading real config
    class _VC:
        container_name = "vc-test"
        container_user = "tester"
        container_working_dir = "/work"

    class _Cfg:
        virtual_computer = _VC()

    rbcm = importlib.import_module("tools.virtual_computer.run_bash_cmd")
    monkeypatch.setattr(rbcm, "load_config", lambda: _Cfg(), raising=True)

    # Mock workspace helper
    monkeypatch.setattr(rbcm, "get_current_workspace_folder", lambda: "ws", raising=True)

    # Mock Podman client and container exec
    class _FakeContainer:
        def __init__(self) -> None:
            self.name = "vc-test"

        def exec_run(self, _args, **_kwargs):  # type: ignore[no-untyped-def]
            return 0, (b"policy-ok\n", b"")

    class _FakeContainerMgr:
        def list(self):  # type: ignore[no-untyped-def]
            return [_FakeContainer()]

    class _FakePodmanClient:
        def __init__(self) -> None:
            self.containers = _FakeContainerMgr()

        def from_env(self):  # type: ignore[no-untyped-def]
            return self

    monkeypatch.setattr(rbcm, "PodmanClient", _FakePodmanClient, raising=True)

    res = await run_bash_cmd("echo policy-ok")
    assert res.exit_code == 0
    assert res.stdout is not None and "policy-ok" in res.stdout
