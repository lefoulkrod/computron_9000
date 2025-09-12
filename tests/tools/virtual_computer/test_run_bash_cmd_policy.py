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


@pytest.mark.asyncio
@pytest.mark.unit
async def test_npm_install_save_dev_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify 'npm install --save-dev jest eslint' not blocked by dev deny pattern."""

    class _VC:
        container_name = "vc-test"
        container_user = "tester"
        container_working_dir = "/work"

    class _Cfg:
        virtual_computer = _VC()

    rbcm = importlib.import_module("tools.virtual_computer.run_bash_cmd")
    monkeypatch.setattr(rbcm, "load_config", lambda: _Cfg(), raising=True)
    monkeypatch.setattr(rbcm, "get_current_workspace_folder", lambda: "ws", raising=True)

    class _FakeContainer:
        name = "vc-test"

        def exec_run(self, _args, **_kwargs):  # type: ignore[no-untyped-def]
            return 0, (b"added 2 packages", b"")

    class _FakeContainerMgr:
        def list(self):  # type: ignore[no-untyped-def]
            return [_FakeContainer()]

    class _FakePodmanClient:
        def __init__(self) -> None:
            self.containers = _FakeContainerMgr()

        def from_env(self):  # type: ignore[no-untyped-def]
            return self

    monkeypatch.setattr(rbcm, "PodmanClient", _FakePodmanClient, raising=True)

    res = await run_bash_cmd("npm install --save-dev jest eslint")
    assert res.exit_code == 0
    assert res.stderr in (None, "")
    assert res.stdout is not None and "added" in res.stdout


@pytest.mark.asyncio
@pytest.mark.unit
async def test_uv_add_dev_pytest_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that 'uv add --dev pytest' is permitted by the policy.

    Mocks container execution to avoid requiring a real container.
    """

    class _VC:
        container_name = "vc-test"
        container_user = "tester"
        container_working_dir = "/work"

    class _Cfg:
        virtual_computer = _VC()

    rbcm = importlib.import_module("tools.virtual_computer.run_bash_cmd")
    monkeypatch.setattr(rbcm, "load_config", lambda: _Cfg(), raising=True)
    monkeypatch.setattr(rbcm, "get_current_workspace_folder", lambda: "ws", raising=True)

    class _FakeContainer:
        name = "vc-test"

        def exec_run(self, _args, **_kwargs):  # type: ignore[no-untyped-def]
            return 0, (b"resolved pytest", b"")

    class _FakeContainerMgr:
        def list(self):  # type: ignore[no-untyped-def]
            return [_FakeContainer()]

    class _FakePodmanClient:
        def __init__(self) -> None:
            self.containers = _FakeContainerMgr()

        def from_env(self):  # type: ignore[no-untyped-def]
            return self

    monkeypatch.setattr(rbcm, "PodmanClient", _FakePodmanClient, raising=True)

    res = await run_bash_cmd("uv add --dev pytest")

    assert res.exit_code == 0
    assert res.stderr in (None, "")
    assert res.stdout is not None and "pytest" in res.stdout


@pytest.mark.asyncio
@pytest.mark.unit
async def test_git_checkout_dev_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """'git checkout dev' should be allowed; 'dev' here is a branch name, not a dev server."""

    class _VC:
        container_name = "vc-test"
        container_user = "tester"
        container_working_dir = "/work"

    class _Cfg:
        virtual_computer = _VC()

    rbcm = importlib.import_module("tools.virtual_computer.run_bash_cmd")
    monkeypatch.setattr(rbcm, "load_config", lambda: _Cfg(), raising=True)
    monkeypatch.setattr(rbcm, "get_current_workspace_folder", lambda: "ws", raising=True)

    class _FakeContainer:
        name = "vc-test"

        def exec_run(self, _args, **_kwargs):  # type: ignore[no-untyped-def]
            return 0, (b"Switched to branch 'dev'", b"")

    class _FakeContainerMgr:
        def list(self):  # type: ignore[no-untyped-def]
            return [_FakeContainer()]

    class _FakePodmanClient:
        def __init__(self) -> None:
            self.containers = _FakeContainerMgr()

        def from_env(self):  # type: ignore[no-untyped-def]
            return self

    monkeypatch.setattr(rbcm, "PodmanClient", _FakePodmanClient, raising=True)

    res = await run_bash_cmd("git checkout dev")

    assert res.exit_code == 0
    assert res.stderr in (None, "")
    assert res.stdout is not None and "branch 'dev'" in res.stdout


@pytest.mark.asyncio
@pytest.mark.unit
async def test_npm_test_watch_false_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """'npm test --watch=false' should be allowed since watch is disabled."""

    class _VC:
        container_name = "vc-test"
        container_user = "tester"
        container_working_dir = "/work"

    class _Cfg:
        virtual_computer = _VC()

    rbcm = importlib.import_module("tools.virtual_computer.run_bash_cmd")
    monkeypatch.setattr(rbcm, "load_config", lambda: _Cfg(), raising=True)
    monkeypatch.setattr(rbcm, "get_current_workspace_folder", lambda: "ws", raising=True)

    class _FakeContainer:
        name = "vc-test"

        def exec_run(self, _args, **_kwargs):  # type: ignore[no-untyped-def]
            return 0, (b"Tests passed", b"")

    class _FakeContainerMgr:
        def list(self):  # type: ignore[no-untyped-def]
            return [_FakeContainer()]

    class _FakePodmanClient:
        def __init__(self) -> None:
            self.containers = _FakeContainerMgr()

        def from_env(self):  # type: ignore[no-untyped-def]
            return self

    monkeypatch.setattr(rbcm, "PodmanClient", _FakePodmanClient, raising=True)

    res = await run_bash_cmd("npm test --watch=false")

    assert res.exit_code == 0
    assert res.stderr in (None, "")
    assert res.stdout is not None and "Tests passed" in res.stdout


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pip_install_package_with_serve_in_name_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Installing packages with 'serve' in the name (e.g., waitress-serve) should be allowed."""

    class _VC:
        container_name = "vc-test"
        container_user = "tester"
        container_working_dir = "/work"

    class _Cfg:
        virtual_computer = _VC()

    rbcm = importlib.import_module("tools.virtual_computer.run_bash_cmd")
    monkeypatch.setattr(rbcm, "load_config", lambda: _Cfg(), raising=True)
    monkeypatch.setattr(rbcm, "get_current_workspace_folder", lambda: "ws", raising=True)

    class _FakeContainer:
        name = "vc-test"

        def exec_run(self, _args, **_kwargs):  # type: ignore[no-untyped-def]
            return 0, (b"Successfully installed waitress-serve", b"")

    class _FakeContainerMgr:
        def list(self):  # type: ignore[no-untyped-def]
            return [_FakeContainer()]

    class _FakePodmanClient:
        def __init__(self) -> None:
            self.containers = _FakeContainerMgr()

        def from_env(self):  # type: ignore[no-untyped-def]
            return self

    monkeypatch.setattr(rbcm, "PodmanClient", _FakePodmanClient, raising=True)

    res = await run_bash_cmd("pip install waitress-serve")

    assert res.exit_code == 0
    assert res.stderr in (None, "")
    assert res.stdout is not None and "Successfully installed" in res.stdout


@pytest.mark.asyncio
@pytest.mark.unit
async def test_block_common_dev_starters() -> None:
    """Ensure typical dev server starters are still blocked."""

    for cmd in (
        "npm run dev",
        "pnpm dev",
        "yarn run dev",
        "bun dev",
        "vite dev",
        "next start",
    ):
        res = await run_bash_cmd(cmd)
        assert res.exit_code == 126
        assert res.stderr is not None and "not allowed" in res.stderr.lower()
