"""Unit tests for desktop tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.desktop._tools import (
    ground,
    keyboard_press,
    keyboard_type,
    mouse_click,
    mouse_double_click,
    mouse_drag,
    screenshot,
    scroll,
)


@pytest.fixture(autouse=True)
def _mock_desktop_deps():
    """Mock out container deps for all tests."""
    with (
        patch("tools.desktop._tools.ensure_desktop_running", new_callable=AsyncMock),
        patch("tools.desktop._tools.capture_screenshot", new_callable=AsyncMock) as mock_capture,
        patch("tools.desktop._tools._run_desktop_cmd", new_callable=AsyncMock) as mock_cmd,
        patch("tools.desktop._tools._run_grounding", new_callable=AsyncMock) as mock_ground,
        patch("tools.desktop._tools.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_capture.return_value = b"\x89PNGfake-png"

        # Default grounding response
        mock_ground.return_value = {
            "thought": "I see the Save button in the toolbar",
            "action": "click(start_box='(100,50)')",
            "action_type": "click",
            "x": 100,
            "y": 50,
            "raw": "Thought: I see the Save button\nAction: click(start_box='(100,50)')",
        }

        yield {
            "cmd": mock_cmd,
            "capture": mock_capture,
            "ground": mock_ground,
        }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ground_returns_action(_mock_desktop_deps):
    """ground() returns formatted action with coordinates."""
    result = await ground("Click the Save button")
    assert "click at (100, 50)" in result
    assert "Save button" in result
    _mock_desktop_deps["ground"].assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ground_type_action(_mock_desktop_deps):
    """ground() formats type actions correctly."""
    _mock_desktop_deps["ground"].return_value = {
        "thought": "I need to type the filename",
        "action": "type(content='report.pdf')",
        "action_type": "type",
        "type_content": "report.pdf",
        "raw": "Thought: I need to type\nAction: type(content='report.pdf')",
    }
    result = await ground("Type the filename")
    assert "type 'report.pdf'" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ground_hotkey_action(_mock_desktop_deps):
    """ground() formats hotkey actions correctly."""
    _mock_desktop_deps["ground"].return_value = {
        "thought": "Save the file",
        "action": "hotkey(key='ctrl+s')",
        "action_type": "hotkey",
        "hotkey": "ctrl+s",
        "raw": "Action: hotkey(key='ctrl+s')",
    }
    result = await ground("Save the file")
    assert "press ctrl+s" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_screenshot_returns_description(_mock_desktop_deps):
    """screenshot() returns the grounding model's description."""
    _mock_desktop_deps["ground"].return_value = {
        "thought": "Desktop shows a file manager window with folders",
        "action": "finished(content='')",
        "action_type": "finished",
        "raw": "Thought: Desktop shows a file manager window with folders",
    }
    result = await screenshot()
    assert "file manager" in result.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mouse_click_executes_xdotool(_mock_desktop_deps):
    """mouse_click() runs xdotool with --sync mousemove."""
    result = await mouse_click(100, 200, button="left")
    _mock_desktop_deps["cmd"].assert_called_once_with(
        "xdotool mousemove --sync 100 200 click 1",
    )
    assert isinstance(result, str)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mouse_click_right_button(_mock_desktop_deps):
    """mouse_click() maps 'right' to button 3."""
    await mouse_click(50, 50, button="right")
    _mock_desktop_deps["cmd"].assert_called_once_with(
        "xdotool mousemove --sync 50 50 click 3",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mouse_double_click(_mock_desktop_deps):
    """mouse_double_click() runs xdotool with --repeat 2 and 500ms delay."""
    await mouse_double_click(300, 400)
    _mock_desktop_deps["cmd"].assert_called_once_with(
        "xdotool mousemove --sync 300 400 click --repeat 2 --delay 500 1",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mouse_drag(_mock_desktop_deps):
    """mouse_drag() runs --sync mousedown/mousemove/mouseup sequence."""
    await mouse_drag(10, 20, 100, 200)
    _mock_desktop_deps["cmd"].assert_called_once_with(
        "xdotool mousemove --sync 10 20 mousedown 1 "
        "mousemove --sync 100 200 mouseup 1",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_keyboard_type(_mock_desktop_deps):
    """keyboard_type() runs xdotool type with shlex-quoted text."""
    await keyboard_type("hello")
    cmd_arg = _mock_desktop_deps["cmd"].call_args[0][0]
    assert "xdotool type" in cmd_arg
    assert "--clearmodifiers" in cmd_arg
    assert "hello" in cmd_arg


@pytest.mark.unit
@pytest.mark.asyncio
async def test_keyboard_type_chunks_long_text(_mock_desktop_deps):
    """keyboard_type() chunks text longer than 50 characters."""
    long_text = "a" * 120
    await keyboard_type(long_text)
    # 120 chars / 50 chunk size = 3 calls
    assert _mock_desktop_deps["cmd"].call_count == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_keyboard_press(_mock_desktop_deps):
    """keyboard_press() runs xdotool key."""
    await keyboard_press("ctrl+c")
    _mock_desktop_deps["cmd"].assert_called_once_with(
        "xdotool key -- ctrl+c",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scroll_down(_mock_desktop_deps):
    """scroll() with direction='down' uses button 5."""
    await scroll(640, 360, direction="down", clicks=5)
    _mock_desktop_deps["cmd"].assert_called_once_with(
        "xdotool mousemove --sync 640 360 click --repeat 5 5",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scroll_up(_mock_desktop_deps):
    """scroll() with direction='up' uses button 4."""
    await scroll(640, 360, direction="up", clicks=3)
    _mock_desktop_deps["cmd"].assert_called_once_with(
        "xdotool mousemove --sync 640 360 click --repeat 3 4",
    )
