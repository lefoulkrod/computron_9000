"""Unit tests for the bbox-based click_at and press_and_hold_at tools."""

from __future__ import annotations

import pytest

from tools.browser import BrowserToolError
from tools.browser.interactions import click_at, press_and_hold_at
from tests.tools.browser.support.playwright_stubs import StubPage


async def _human_click_at_passthrough(
    target: object, x1: float, y1: float, x2: float, y2: float,
) -> None:
    """No-op passthrough for human_click_at."""


async def _human_press_and_hold_at_passthrough(
    target: object,
    x1: float, y1: float, x2: float, y2: float,
    duration_ms: int = 3000,
) -> None:
    """No-op passthrough for human_press_and_hold_at."""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_click_at_basic(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    """Clicking at a valid bbox returns a valid snapshot."""
    page = StubPage(
        title="Test Page",
        body_text="Some content",
        url="https://example.test/page",
    )
    patch_interactions_browser(page)
    monkeypatch.setattr(
        "tools.browser.interactions.human_click_at",
        _human_click_at_passthrough,
    )

    result = await click_at(50, 100, 150, 200)
    assert isinstance(result, str)
    assert "[Page:" in result
    assert settle_tracker["count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_click_at_accepts_int_and_float(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    """click_at accepts both int and float coordinates."""
    captured: list[tuple[float, float, float, float]] = []

    async def _capture(
        target: object, x1: float, y1: float, x2: float, y2: float,
    ) -> None:
        captured.append((x1, y1, x2, y2))

    page = StubPage(url="https://example.test/page")
    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_click_at", _capture)

    await click_at(50, 75, 150, 200)
    assert captured[-1] == (50.0, 75.0, 150.0, 200.0)

    await click_at(10.5, 20.3, 100.7, 200.9)
    assert captured[-1] == (10.5, 20.3, 100.7, 200.9)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_click_at_rejects_non_finite(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
) -> None:
    """NaN and Inf coordinates are rejected."""
    page = StubPage(url="https://example.test/page")
    patch_interactions_browser(page)
    monkeypatch.setattr(
        "tools.browser.interactions.human_click_at",
        _human_click_at_passthrough,
    )

    with pytest.raises(BrowserToolError, match="finite"):
        await click_at(float("nan"), 100, 200, 300)

    with pytest.raises(BrowserToolError, match="finite"):
        await click_at(100, 200, 300, float("inf"))

    with pytest.raises(BrowserToolError, match="finite"):
        await click_at(float("-inf"), float("nan"), 200, 300)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_click_at_rejects_non_numeric(
    patch_interactions_browser,
) -> None:
    """Non-numeric coordinates are rejected."""
    page = StubPage(url="https://example.test/page")
    patch_interactions_browser(page)

    with pytest.raises(BrowserToolError, match="numeric"):
        await click_at("abc", 100, 200, 300)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_click_at_about_blank(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
) -> None:
    """Clicking on about:blank raises a helpful error."""
    page = StubPage(url="about:blank", body_text="")
    patch_interactions_browser(page)
    monkeypatch.setattr(
        "tools.browser.interactions.human_click_at",
        _human_click_at_passthrough,
    )

    with pytest.raises(BrowserToolError, match="Navigate"):
        await click_at(50, 100, 150, 200)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_press_and_hold_at_basic(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    """Pressing and holding at a bbox returns a valid snapshot."""
    page = StubPage(
        title="Challenge",
        body_text="Hold to verify",
        url="https://example.test/challenge",
    )
    patch_interactions_browser(page)
    monkeypatch.setattr(
        "tools.browser.interactions.human_press_and_hold_at",
        _human_press_and_hold_at_passthrough,
    )

    result = await press_and_hold_at(200, 300, 400, 500, duration_ms=3000)
    assert isinstance(result, str)
    assert "[Page:" in result
    assert settle_tracker["count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_press_and_hold_at_clamps_duration(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    """Duration is clamped to 500-10000 range."""
    captured_durations: list[int] = []

    async def _capture(
        target: object,
        x1: float, y1: float, x2: float, y2: float,
        duration_ms: int = 3000,
    ) -> None:
        captured_durations.append(duration_ms)

    page = StubPage(url="https://example.test/challenge")
    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_press_and_hold_at", _capture)

    # Below minimum: should clamp to 500
    await press_and_hold_at(50, 100, 150, 200, duration_ms=100)
    assert captured_durations[-1] == 500

    # Above maximum: should clamp to 10000
    await press_and_hold_at(50, 100, 150, 200, duration_ms=99999)
    assert captured_durations[-1] == 10000

    # Within range: should pass through
    await press_and_hold_at(50, 100, 150, 200, duration_ms=5000)
    assert captured_durations[-1] == 5000


@pytest.mark.unit
@pytest.mark.asyncio
async def test_press_and_hold_at_rejects_non_finite(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
) -> None:
    """NaN and Inf coordinates are rejected for press_and_hold_at."""
    page = StubPage(url="https://example.test/page")
    patch_interactions_browser(page)
    monkeypatch.setattr(
        "tools.browser.interactions.human_press_and_hold_at",
        _human_press_and_hold_at_passthrough,
    )

    with pytest.raises(BrowserToolError, match="finite"):
        await press_and_hold_at(float("nan"), 100, 200, 300)

    with pytest.raises(BrowserToolError, match="finite"):
        await press_and_hold_at(100, 200, 300, float("inf"))
