"""Unit tests for the press_and_hold browser interaction tool."""

from __future__ import annotations

import pytest

from tools.browser import BrowserToolError
from tools.browser.interactions import press_and_hold
from tests.tools.browser.support.playwright_stubs import StubLocator, StubPage


async def _human_press_and_hold_passthrough(
    page: object, locator: StubLocator, duration_ms: int = 3000
) -> None:
    """Passthrough that clicks the locator to trigger navigation stubs."""
    await locator.click()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_press_and_hold_basic(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    """Pressing and holding a role-matched element returns a valid snapshot."""
    page = StubPage(
        title="Bot Challenge",
        body_text="Press and hold to verify",
        url="https://example.test/challenge",
    )
    page.add_role_locator(
        "button",
        name="Press and hold to verify",
        tag="button",
    )
    patch_interactions_browser(page)
    monkeypatch.setattr(
        "tools.browser.interactions.human_press_and_hold",
        _human_press_and_hold_passthrough,
    )

    result = await press_and_hold("button:Press and hold to verify", duration_ms=3000)
    assert isinstance(result, str)
    assert "[Page:" in result
    assert settle_tracker["count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_press_and_hold_empty_selector(
    patch_interactions_browser,
) -> None:
    """Empty selector raises BrowserToolError before accessing the browser."""
    page = StubPage(url="https://example.test/page")
    patch_interactions_browser(page)

    with pytest.raises(BrowserToolError, match="non-empty"):
        await press_and_hold("   ")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_press_and_hold_about_blank(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
) -> None:
    """Pressing on about:blank raises a helpful error."""
    page = StubPage(url="about:blank", body_text="")
    patch_interactions_browser(page)
    monkeypatch.setattr(
        "tools.browser.interactions.human_press_and_hold",
        _human_press_and_hold_passthrough,
    )

    with pytest.raises(BrowserToolError, match="Navigate"):
        await press_and_hold("button:Hold Me")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_press_and_hold_not_found(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
) -> None:
    """Raises BrowserToolError when element can't be located."""
    page = StubPage(
        title="Challenge",
        body_text="Page content",
        url="https://example.test/challenge",
    )
    patch_interactions_browser(page)
    monkeypatch.setattr(
        "tools.browser.interactions.human_press_and_hold",
        _human_press_and_hold_passthrough,
    )

    with pytest.raises(BrowserToolError):
        await press_and_hold("button:Does Not Exist")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_press_and_hold_duration_clamped(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    """Duration is clamped to 500-10000 range and passed to human helper."""
    captured_durations: list[int] = []

    async def _capture_duration(page: object, locator: object, duration_ms: int = 3000) -> None:
        captured_durations.append(duration_ms)

    page = StubPage(
        title="Challenge",
        body_text="Hold button",
        url="https://example.test/challenge",
    )
    page.add_role_locator("button", name="Hold Me", tag="button")
    patch_interactions_browser(page)
    monkeypatch.setattr(
        "tools.browser.interactions.human_press_and_hold",
        _capture_duration,
    )

    # Below minimum: should clamp to 500
    await press_and_hold("button:Hold Me", duration_ms=100)
    assert captured_durations[-1] == 500

    # Above maximum: should clamp to 10000
    await press_and_hold("button:Hold Me", duration_ms=99999)
    assert captured_durations[-1] == 10000

    # Within range: should pass through
    await press_and_hold("button:Hold Me", duration_ms=5000)
    assert captured_durations[-1] == 5000
