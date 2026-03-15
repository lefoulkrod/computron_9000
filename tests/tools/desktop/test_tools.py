"""Unit tests for desktop tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.desktop._tools import (
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
    """Mock out container and vision deps for all tests."""
    with (
        patch("tools.desktop._tools.ensure_desktop_running", new_callable=AsyncMock),
        patch("tools.desktop._tools.capture_screenshot", new_callable=AsyncMock) as mock_capture,
        patch("tools.desktop._tools._run_desktop_cmd", new_callable=AsyncMock) as mock_cmd,
        patch("tools.desktop._tools.load_config") as mock_config,
        patch("tools.desktop._tools.AsyncClient") as mock_client_cls,
    ):
        # Set up config
        cfg = MagicMock()
        cfg.vision.model = "test-model"
        cfg.vision.options = {}
        cfg.vision.think = False
        cfg.llm.host = None
        mock_config.return_value = cfg

        # Set up screenshot
        mock_capture.return_value = b"\xff\xd8fake-jpeg"

        # Set up vision model response
        mock_response = MagicMock()
        mock_response.response = "Desktop shows a file manager window."
        client_instance = AsyncMock()
        client_instance.generate = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = client_instance

        yield {
            "cmd": mock_cmd,
            "capture": mock_capture,
            "client": client_instance,
        }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_screenshot_returns_description():
    """screenshot() returns the vision model's text description."""
    result = await screenshot()
    assert "file manager" in result.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mouse_click_executes_xdotool(_mock_desktop_deps):
    """mouse_click() runs the correct xdotool command."""
    result = await mouse_click(100, 200, button="left")
    _mock_desktop_deps["cmd"].assert_called_once_with(
        "xdotool mousemove 100 200 click 1",
    )
    assert isinstance(result, str)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mouse_click_right_button(_mock_desktop_deps):
    """mouse_click() maps 'right' to button 3."""
    await mouse_click(50, 50, button="right")
    _mock_desktop_deps["cmd"].assert_called_once_with(
        "xdotool mousemove 50 50 click 3",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mouse_double_click(_mock_desktop_deps):
    """mouse_double_click() runs xdotool with --repeat 2."""
    await mouse_double_click(300, 400)
    _mock_desktop_deps["cmd"].assert_called_once_with(
        "xdotool mousemove 300 400 click --repeat 2 --delay 100 1",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mouse_drag(_mock_desktop_deps):
    """mouse_drag() runs mousedown/mousemove/mouseup sequence."""
    await mouse_drag(10, 20, 100, 200)
    _mock_desktop_deps["cmd"].assert_called_once_with(
        "xdotool mousemove 10 20 mousedown 1 mousemove --sync 100 200 mouseup 1",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_keyboard_type(_mock_desktop_deps):
    """keyboard_type() runs xdotool type."""
    await keyboard_type("hello")
    cmd_arg = _mock_desktop_deps["cmd"].call_args[0][0]
    assert "xdotool type" in cmd_arg
    assert "hello" in cmd_arg


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
        "xdotool mousemove 640 360 click --repeat 5 5",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scroll_up(_mock_desktop_deps):
    """scroll() with direction='up' uses button 4."""
    await scroll(640, 360, direction="up", clicks=3)
    _mock_desktop_deps["cmd"].assert_called_once_with(
        "xdotool mousemove 640 360 click --repeat 3 4",
    )
