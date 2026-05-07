"""Unit tests for desktop tools."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools._grounding import GroundingResponse
from tools.desktop._tools import (
    describe_screen,
    keyboard_press,
    keyboard_type,
    mouse_click,
    mouse_double_click,
    mouse_drag,
    perform_visual_action,
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
    fake_settings = {
        "vision_model": "qwen3.5:4b",
        "vision_options": {"temperature": 0.1, "num_predict": 512},
        "vision_think": False,
    }

    async def _fake_vision_generate(prompt, image_base64, *, media_type="image/png"):
        return "A desktop with a terminal and file manager."

    with (
        patch("settings.load_settings", return_value=fake_settings),
        patch("tools.desktop._tools.capture_screenshot", new_callable=AsyncMock) as mock_capture,
        patch("sdk.providers.vision_generate", _fake_vision_generate),
    ):
        mock_capture.return_value = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        yield {"capture": mock_capture}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_describe_screen_returns_vision_response(_mock_vision_deps):
    """describe_screen() returns the vision model's text description."""
    result = await describe_screen()
    assert "terminal" in result.lower()
    assert "file manager" in result.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_describe_screen_no_vision_model():
    """describe_screen() returns error when no vision model configured."""
    from sdk.providers import ProviderError

    fake_settings = {"vision_model": "", "vision_options": {}, "vision_think": False}

    async def _raises_no_model(*args, **kwargs):
        raise ValueError("No vision model configured. Set one in Settings > System.")

    with (
        patch("tools.desktop._tools.ensure_desktop_running", new_callable=AsyncMock),
        patch("settings.load_settings", return_value=fake_settings),
        patch("tools.desktop._tools.capture_screenshot", new_callable=AsyncMock) as mock_capture,
        patch("sdk.providers.vision_generate", _raises_no_model),
    ):
        mock_capture.return_value = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
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
async def test_describe_screen_vision_model_failure():
    """describe_screen() returns error when vision model fails."""
    from sdk.providers import ProviderError

    fake_settings = {
        "vision_model": "qwen3.5:4b",
        "vision_options": {},
        "vision_think": False,
    }

    async def _failing_vision(*args, **kwargs):
        raise ProviderError("model timeout", retryable=False)

    with (
        patch("settings.load_settings", return_value=fake_settings),
        patch("tools.desktop._tools.capture_screenshot", new_callable=AsyncMock) as mock_capture,
        patch("sdk.providers.vision_generate", _failing_vision),
    ):
        mock_capture.return_value = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        result = await describe_screen()
    assert "error" in result.lower()
    assert "model timeout" in result.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_describe_screen_empty_response():
    """describe_screen() returns error when vision model returns empty."""
    fake_settings = {
        "vision_model": "qwen3.5:4b",
        "vision_options": {},
        "vision_think": False,
    }

    async def _empty_vision(*args, **kwargs):
        return ""

    with (
        patch("settings.load_settings", return_value=fake_settings),
        patch("tools.desktop._tools.capture_screenshot", new_callable=AsyncMock) as mock_capture,
        patch("sdk.providers.vision_generate", _empty_vision),
    ):
        mock_capture.return_value = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
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


# ── perform_visual_action ────────────────────────────────────────────


def _grounding_response(**kwargs) -> GroundingResponse:
    """Build a GroundingResponse with defaults."""
    defaults = {"x": 100, "y": 200, "thought": "test", "action_type": "click", "raw": {}}
    defaults.update(kwargs)
    return GroundingResponse(**defaults)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_visual_action_click(_mock_desktop_deps):
    """perform_visual_action() sends screenshot to grounding and executes click."""
    response = _grounding_response(action_type="click", x=300, y=400)
    with (
        patch("tools.desktop._tools.capture_screenshot", new_callable=AsyncMock) as mock_cap,
        patch("tools._grounding.run_grounding", new_callable=AsyncMock) as mock_ground,
    ):
        mock_cap.return_value = b"\x89PNG"
        mock_ground.return_value = response

        result = await perform_visual_action("Click the button")

        mock_ground.assert_called_once_with(
            b"\x89PNG", "Click the button",
            screenshot_filename="desktop_visual_action.png",
        )
        _mock_desktop_deps["cmd"].assert_called_with(
            "xdotool mousemove --sync 300 400 click 1",
        )
        assert "Save" in result  # a11y tree observation returned


@pytest.mark.unit
@pytest.mark.asyncio
async def test_visual_action_type(_mock_desktop_deps):
    """perform_visual_action() executes type action from grounding response."""
    response = _grounding_response(
        action_type="type", x=None, y=None,
        raw={"type_content": "hello"},
    )
    with (
        patch("tools.desktop._tools.capture_screenshot", new_callable=AsyncMock) as mock_cap,
        patch("tools._grounding.run_grounding", new_callable=AsyncMock) as mock_ground,
    ):
        mock_cap.return_value = b"\x89PNG"
        mock_ground.return_value = response

        result = await perform_visual_action("Type hello")

        cmd_arg = _mock_desktop_deps["cmd"].call_args[0][0]
        assert "xdotool type" in cmd_arg
        assert "hello" in cmd_arg


@pytest.mark.unit
@pytest.mark.asyncio
async def test_visual_action_hotkey(_mock_desktop_deps):
    """perform_visual_action() normalises hotkey names for xdotool."""
    response = _grounding_response(
        action_type="hotkey", x=None, y=None,
        raw={"hotkey": "ctrl+c"},
    )
    with (
        patch("tools.desktop._tools.capture_screenshot", new_callable=AsyncMock) as mock_cap,
        patch("tools._grounding.run_grounding", new_callable=AsyncMock) as mock_ground,
    ):
        mock_cap.return_value = b"\x89PNG"
        mock_ground.return_value = response

        await perform_visual_action("Copy text")

        _mock_desktop_deps["cmd"].assert_called_with("xdotool key -- ctrl+c")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_visual_action_screenshot_failure(_mock_desktop_deps):
    """perform_visual_action() returns error when screenshot fails."""
    with patch("tools.desktop._tools.capture_screenshot", new_callable=AsyncMock) as mock_cap:
        mock_cap.side_effect = RuntimeError("capture failed")
        result = await perform_visual_action("Click something")
        assert "Error" in result
        assert "capture failed" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_visual_action_grounding_failure(_mock_desktop_deps):
    """perform_visual_action() returns error when grounding server fails."""
    with (
        patch("tools.desktop._tools.capture_screenshot", new_callable=AsyncMock) as mock_cap,
        patch("tools._grounding.run_grounding", new_callable=AsyncMock) as mock_ground,
    ):
        mock_cap.return_value = b"\x89PNG"
        mock_ground.side_effect = RuntimeError("server down")
        result = await perform_visual_action("Click something")
        assert "Error" in result
        assert "server down" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_visual_action_empty_task(_mock_desktop_deps):
    """perform_visual_action() rejects empty task strings."""
    result = await perform_visual_action("   ")
    assert "Error" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_visual_action_finished(_mock_desktop_deps):
    """perform_visual_action() handles 'finished' action type."""
    response = _grounding_response(
        action_type="finished", x=None, y=None,
        raw={"finished_content": "Task complete"},
    )
    with (
        patch("tools.desktop._tools.capture_screenshot", new_callable=AsyncMock) as mock_cap,
        patch("tools._grounding.run_grounding", new_callable=AsyncMock) as mock_ground,
    ):
        mock_cap.return_value = b"\x89PNG"
        mock_ground.return_value = response

        result = await perform_visual_action("Do the thing")

        assert "finished" in result.lower()
        assert "Task complete" in result
