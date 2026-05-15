"""Tests for the action dispatch layer (tools/browser/_action_map.py)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools._grounding import GroundingResponse
from tools.browser._action_map import _normalize_hotkey, execute_action
from tools.browser.core.exceptions import BrowserToolError


# ── Helpers ────────────────────────────────────────────────────────────


def _make_page() -> MagicMock:
    """Create a mock Page with keyboard."""
    page = MagicMock()
    page.keyboard = MagicMock()
    page.keyboard.type = AsyncMock()
    page.mouse = MagicMock()
    return page


def _make_response(
    action_type: str,
    *,
    x: int | None = None,
    y: int | None = None,
    raw: dict | None = None,
) -> GroundingResponse:
    return GroundingResponse(
        x=x,
        y=y,
        thought="test",
        action_type=action_type,
        raw=raw or {},
    )


# ── _normalize_hotkey tests ───────────────────────────────────────────


@pytest.mark.unit
class TestNormalizeHotkey:
    def test_ctrl_c(self) -> None:
        assert _normalize_hotkey("ctrl+c") == "Control+c"

    def test_ctrl_shift_p(self) -> None:
        assert _normalize_hotkey("Ctrl+Shift+P") == "Control+Shift+P"

    def test_esc(self) -> None:
        assert _normalize_hotkey("esc") == "Escape"

    def test_escape(self) -> None:
        assert _normalize_hotkey("escape") == "Escape"

    def test_enter(self) -> None:
        assert _normalize_hotkey("enter") == "Enter"

    def test_return(self) -> None:
        assert _normalize_hotkey("return") == "Enter"

    def test_plain_key(self) -> None:
        assert _normalize_hotkey("a") == "a"

    def test_arrow_keys(self) -> None:
        assert _normalize_hotkey("up") == "ArrowUp"
        assert _normalize_hotkey("down") == "ArrowDown"

    def test_space(self) -> None:
        assert _normalize_hotkey("space") == " "

    def test_meta_aliases(self) -> None:
        assert _normalize_hotkey("cmd+c") == "Meta+c"
        assert _normalize_hotkey("win+e") == "Meta+e"
        assert _normalize_hotkey("super+l") == "Meta+l"


# ── execute_action tests ─────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_click_action() -> None:
    """Click action should call human_click_at with bbox around coordinates."""
    page = _make_page()
    response = _make_response("click", x=100, y=200)

    with patch("tools.browser._action_map.human_click_at", new_callable=AsyncMock) as mock:
        await execute_action(response, page, page)
        mock.assert_called_once_with(page, 95, 195, 105, 205)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_left_double_action() -> None:
    """Double-click action should call human_double_click_at."""
    page = _make_page()
    response = _make_response("left_double", x=50, y=75)

    with patch("tools.browser._action_map.human_double_click_at", new_callable=AsyncMock) as mock:
        await execute_action(response, page, page)
        mock.assert_called_once_with(page, 45, 70, 55, 80)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_right_single_action() -> None:
    """Right-click action should call human_right_click_at."""
    page = _make_page()
    response = _make_response("right_single", x=300, y=400)

    with patch("tools.browser._action_map.human_right_click_at", new_callable=AsyncMock) as mock:
        await execute_action(response, page, page)
        mock.assert_called_once_with(page, 295, 395, 305, 405)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_drag_action() -> None:
    """Drag action should call human_drag_at with source and dest bboxes."""
    page = _make_page()
    response = _make_response(
        "drag",
        x=100,
        y=200,
        raw={
            "coordinates": [
                {"screen": [100, 200]},
                {"screen": [300, 400]},
            ],
        },
    )

    with patch("tools.browser._action_map.human_drag_at", new_callable=AsyncMock) as mock:
        await execute_action(response, page, page)
        mock.assert_called_once_with(
            page,
            95, 195, 105, 205,   # source bbox
            295, 395, 305, 405,  # dest bbox
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_drag_insufficient_coords() -> None:
    """Drag with fewer than 2 coordinate pairs should raise."""
    page = _make_page()
    response = _make_response(
        "drag",
        x=100,
        y=200,
        raw={"coordinates": [{"screen": [100, 200]}]},
    )

    with pytest.raises(BrowserToolError, match="two coordinate pairs"):
        await execute_action(response, page, page)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_type_action() -> None:
    """Type action should call page.keyboard.type."""
    page = _make_page()
    response = _make_response("type", raw={"type_content": "hello"})

    await execute_action(response, page, page)
    page.keyboard.type.assert_called_once()
    call_args = page.keyboard.type.call_args
    assert call_args[0][0] == "hello"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_hotkey_action() -> None:
    """Hotkey action should call human_press_keys with normalized key."""
    page = _make_page()
    response = _make_response("hotkey", raw={"hotkey": "ctrl+c"})

    with patch("tools.browser._action_map.human_press_keys", new_callable=AsyncMock) as mock:
        await execute_action(response, page, page)
        mock.assert_called_once_with(page, ["Control+c"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_hotkey_missing_key() -> None:
    """Hotkey with empty key should raise."""
    page = _make_page()
    response = _make_response("hotkey", raw={})

    with pytest.raises(BrowserToolError, match="missing 'hotkey' field"):
        await execute_action(response, page, page)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scroll_action() -> None:
    """Scroll action should call human_scroll."""
    page = _make_page()
    response = _make_response("scroll", x=500, y=500, raw={"scroll_direction": "up"})

    with patch("tools.browser._action_map.human_scroll", new_callable=AsyncMock) as mock:
        await execute_action(response, page, page)
        mock.assert_called_once_with(page, direction="up")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_wait_action() -> None:
    """Wait action should sleep without error."""
    page = _make_page()
    response = _make_response("wait")

    with patch("tools.browser._action_map.asyncio.sleep", new_callable=AsyncMock) as mock:
        await execute_action(response, page, page)
        mock.assert_called_once_with(1.0)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_finished_action() -> None:
    """Finished action should be a no-op."""
    page = _make_page()
    response = _make_response("finished")

    # Should not raise
    await execute_action(response, page, page)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unknown_action() -> None:
    """Unknown action type should log a warning but not raise."""
    page = _make_page()
    response = _make_response("teleport")

    # Should complete without raising.
    await execute_action(response, page, page)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_click_missing_coords() -> None:
    """Click without coordinates should raise."""
    page = _make_page()
    response = _make_response("click")

    with pytest.raises(BrowserToolError, match="requires coordinates"):
        await execute_action(response, page, page)
