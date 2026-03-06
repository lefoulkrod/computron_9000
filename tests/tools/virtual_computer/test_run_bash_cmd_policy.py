"""Policy tests for run_bash_cmd allow/deny validation."""

from __future__ import annotations

import pytest

from tools.virtual_computer._policy import is_allowed_command


@pytest.mark.unit
def test_denylist_blocks_http_server() -> None:
    """http.server should be blocked by denylist."""
    assert not is_allowed_command("python -m http.server 8000")


@pytest.mark.unit
def test_allowlist_allows_echo() -> None:
    """A harmless echo command should be allowed."""
    assert is_allowed_command("echo policy-ok")


@pytest.mark.unit
def test_npm_install_save_dev_allowed() -> None:
    """'npm install --save-dev jest eslint' should not be blocked by dev deny pattern."""
    assert is_allowed_command("npm install --save-dev jest eslint")


@pytest.mark.unit
def test_uv_add_dev_pytest_allowed() -> None:
    """'uv add --dev pytest' should be permitted by the policy."""
    assert is_allowed_command("uv add --dev pytest")


@pytest.mark.unit
def test_git_checkout_dev_allowed() -> None:
    """'git checkout dev' should be allowed; 'dev' here is a branch name, not a dev server."""
    assert is_allowed_command("git checkout dev")


@pytest.mark.unit
def test_npm_test_watch_false_allowed() -> None:
    """'npm test --watch=false' should be allowed since watch is explicitly disabled."""
    assert is_allowed_command("npm test --watch=false")


@pytest.mark.unit
def test_pip_install_package_with_serve_in_name_allowed() -> None:
    """Installing packages with 'serve' in the name should be allowed."""
    assert is_allowed_command("pip install waitress-serve")


@pytest.mark.unit
def test_block_pip_install_torch() -> None:
    """Reinstalling torch/torchvision should be blocked to protect the CUDA build."""
    for cmd in (
        "pip install torch",
        "pip3 install torch",
        "pip install torchvision",
        "pip install diffusers torch",
        "pip install torch torchvision",
    ):
        assert not is_allowed_command(cmd), f"Expected block for: {cmd}"


@pytest.mark.unit
def test_allow_torch_related_packages() -> None:
    """Packages with 'torch' as a prefix (e.g. torchaudio) should be allowed."""
    for cmd in (
        "pip install torchaudio",
        "pip install torch-geometric",
        "pip install pytorch-lightning",
    ):
        assert is_allowed_command(cmd), f"Expected allow for: {cmd}"


@pytest.mark.unit
def test_block_common_dev_starters() -> None:
    """Ensure typical dev server starters are blocked."""
    for cmd in (
        "npm run dev",
        "pnpm dev",
        "yarn run dev",
        "bun dev",
        "vite dev",
        "next start",
    ):
        assert not is_allowed_command(cmd), f"Expected block for: {cmd}"


@pytest.mark.unit
def test_empty_command_blocked() -> None:
    """Empty or whitespace-only commands should be blocked."""
    assert not is_allowed_command("")
    assert not is_allowed_command("   ")
