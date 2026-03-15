"""Unit tests for desktop tools."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.desktop._tools import (
    describe_screen,
    keyboard_press,
    keyboard_type,
    mouse_click,
    mouse_double_click,
    mouse_drag,
    read_screen,
    scroll,
)


@pytest.fixture(autouse=True)
def _mock_desktop_deps():
    """Mock out container deps for all tests."""
    with (
        patch("tools.desktop._tools.ensure_desktop_running", new_callable=AsyncMock),
        patch("tools.desktop._tools._run_desktop_cmd", new_callable=AsyncMock) as mock_cmd,
        patch("tools.desktop._tools._get_a11y_tree", new_callable=AsyncMock) as mock_a11y,
        patch("tools.desktop._tools.asyncio.sleep", new_callable=AsyncMock),
    ):
        # Default a11y tree
        mock_a11y.return_value = [
            {"role": "push button", "label": "Save", "x": 90, "y": 40, "w": 60, "h": 30},
            {"role": "push button", "label": "Cancel", "x": 160, "y": 40, "w": 60, "h": 30},
        ]

        yield {
            "cmd": mock_cmd,
            "a11y": mock_a11y,
        }


# ── read_screen ──────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_read_screen_includes_a11y_elements(_mock_desktop_deps):
    """read_screen() includes numbered interactive elements from a11y tree."""
    result = await read_screen()
    assert "[1]" in result
    assert "Save" in result
    assert "[2]" in result
    assert "Cancel" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_read_screen_a11y_shows_click_coordinates(_mock_desktop_deps):
    """a11y elements include center-point click coordinates."""
    result = await read_screen()
    # Save button: x=90, y=40, w=60, h=30 → center (120, 55)
    assert "(120, 55)" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_read_screen_empty_a11y(_mock_desktop_deps):
    """read_screen() returns fallback text when a11y tree is empty."""
    _mock_desktop_deps["a11y"].return_value = []
    result = await read_screen()
    assert "no interactive elements" in result.lower()


# ── describe_screen ──────────────────────────────────────────────────


@pytest.fixture
def _mock_vision_deps():
    """Mock vision model deps for describe_screen tests."""
    mock_config = MagicMock()
    mock_config.desktop.vision_model = "qwen3.5:4b"
    mock_config.llm.host = None

    with (
        patch("tools.desktop._tools.load_config", return_value=mock_config),
        patch("tools.desktop._tools.capture_screenshot", new_callable=AsyncMock) as mock_capture,
        patch("tools.desktop._tools.AsyncClient") as mock_client_cls,
    ):
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_capture.return_value = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        yield {
            "config": mock_config,
            "capture": mock_capture,
            "client_cls": mock_client_cls,
            "client": mock_client,
        }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_describe_screen_returns_vision_response(_mock_vision_deps):
    """describe_screen() returns the vision model's text description."""
    _mock_vision_deps["client"].chat.return_value = {
        "message": {"content": "A desktop with a terminal and file manager."},
    }
    result = await describe_screen()
    assert "terminal" in result.lower()
    assert "file manager" in result.lower()
    _mock_vision_deps["client"].chat.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_describe_screen_no_vision_model():
    """describe_screen() returns error when no vision model configured."""
    mock_config = MagicMock()
    mock_config.desktop.vision_model = None
    with (
        patch("tools.desktop._tools.ensure_desktop_running", new_callable=AsyncMock),
        patch("tools.desktop._tools.load_config", return_value=mock_config),
    ):
        result = await describe_screen()
        assert "error" in result.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_describe_screen_capture_failure(_mock_vision_deps):
    """describe_screen() returns error when screenshot capture fails."""
    _mock_vision_deps["capture"].side_effect = RuntimeError("capture failed")
    result = await describe_screen()
    assert "error" in result.lower()
    assert "capture failed" in result.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_describe_screen_vision_model_failure(_mock_vision_deps):
    """describe_screen() returns error when vision model fails."""
    _mock_vision_deps["client"].chat.side_effect = Exception("model timeout")
    result = await describe_screen()
    assert "error" in result.lower()
    assert "model timeout" in result.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_describe_screen_empty_response(_mock_vision_deps):
    """describe_screen() returns error when vision model returns empty."""
    _mock_vision_deps["client"].chat.return_value = {
        "message": {"content": ""},
    }
    result = await describe_screen()
    assert "error" in result.lower()
    assert "empty" in result.lower()


# ── mouse actions ─────────────────────────────────────────────────────


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
    """mouse_double_click() runs xdotool with --repeat 2."""
    await mouse_double_click(300, 400)
    _mock_desktop_deps["cmd"].assert_called_once_with(
        "xdotool mousemove --sync 300 400 click --repeat 2 --delay 100 1",
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


# ── keyboard ──────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_keyboard_type(_mock_desktop_deps):
    """keyboard_type() uses xdotool type with chunking."""
    await keyboard_type("hello world")
    cmd_arg = _mock_desktop_deps["cmd"].call_args[0][0]
    assert "xdotool type" in cmd_arg
    assert "hello world" in cmd_arg


@pytest.mark.unit
@pytest.mark.asyncio
async def test_keyboard_press(_mock_desktop_deps):
    """keyboard_press() runs xdotool key."""
    await keyboard_press("ctrl+c")
    _mock_desktop_deps["cmd"].assert_called_once_with(
        "xdotool key -- ctrl+c",
    )


# ── scroll ────────────────────────────────────────────────────────────


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
