"""Integration test for run_bash_cmd tool in the os package."""

import asyncio
import pytest

from tools.virtual_computer.run_bash_cmd import run_bash_cmd, RunBashCmdError, BashCmdResult

@pytest.mark.asyncio
@pytest.mark.integration
async def test_run_bash_cmd_echo_success() -> None:
    """Test run_bash_cmd executes a simple echo command successfully.

    Verifies BashCmdResult fields for expected output and exit code.
    """
    result = await run_bash_cmd("echo hello-world")
    assert isinstance(result, BashCmdResult)
    assert result.stdout is not None and "hello-world" in result.stdout
    assert result.stderr in (None, "")
    assert isinstance(result.exit_code, int) and result.exit_code == 0

@pytest.mark.asyncio
@pytest.mark.integration
async def test_run_bash_cmd_invalid_command() -> None:
    """Test run_bash_cmd with an invalid command raises RunBashCmdError and returns stderr.
    """
    result = await run_bash_cmd("nonexistent_command_xyz")
    assert isinstance(result, BashCmdResult)
    assert result.stdout in (None, "")
    assert result.stderr is not None and "not found" in result.stderr
    assert isinstance(result.exit_code, int) and result.exit_code != 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_run_bash_cmd_multiline_backslash() -> None:
    """Test run_bash_cmd executes a multiline command using backslashes."""
    cmd = "echo 'line1' && \\\necho 'line2' && \\\necho 'line3'"
    result = await run_bash_cmd(cmd)
    assert isinstance(result, BashCmdResult)
    assert result.exit_code == 0
    assert result.stdout is not None
    assert "line1" in result.stdout
    assert "line2" in result.stdout
    assert "line3" in result.stdout
    assert result.stderr in (None, "")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_run_bash_cmd_multiline_heredoc() -> None:
    """Test run_bash_cmd executes a multiline command using a here document."""
    cmd = """bash <<EOF\necho 'heredoc1'\necho 'heredoc2'\necho 'heredoc3'\nEOF"""
    result = await run_bash_cmd(cmd)
    assert isinstance(result, BashCmdResult)
    assert result.exit_code == 0
    assert result.stdout is not None
    assert "heredoc1" in result.stdout
    assert "heredoc2" in result.stdout
    assert "heredoc3" in result.stdout
    assert result.stderr in (None, "")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_run_bash_cmd_multiline_subshell() -> None:
    """Test run_bash_cmd executes a multiline command using curly braces subshell."""
    cmd = """{ echo 'subshell1'; echo 'subshell2'; echo 'subshell3'; }"""
    result = await run_bash_cmd(cmd)
    assert isinstance(result, BashCmdResult)
    assert result.exit_code == 0
    assert result.stdout is not None
    assert "subshell1" in result.stdout
    assert "subshell2" in result.stdout
    assert "subshell3" in result.stdout
    assert result.stderr in (None, "")
