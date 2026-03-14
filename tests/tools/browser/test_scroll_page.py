from __future__ import annotations

import pytest

from config import load_config
from tools.browser import BrowserToolError
from tools.browser.interactions import scroll_page

_cfg = load_config()
_SCROLL_WARN_THRESHOLD = _cfg.tools.browser.scroll_warn_threshold
_SCROLL_HARD_LIMIT = _cfg.tools.browser.scroll_hard_limit
from tests.tools.browser.support.playwright_stubs import StubPage


def _make_scroll_setup(monkeypatch, patch_interactions_browser, settle_tracker):
    """Create a page + fake scroll setup for scroll budget tests."""
    page = StubPage(
        title="Start",
        body_text="body text",
        url="https://example.test/start",
    )
    page.set_scroll_state(scroll_top=0, viewport_height=600, document_height=2000)
    patch_interactions_browser(page)

    async def fake_human_scroll(page_arg: object, direction: str = "down", amount: int | None = None) -> None:
        assert page_arg is page

    monkeypatch.setattr("tools.browser.interactions.human_scroll", fake_human_scroll)
    return page


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scroll_page_delegates(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    page = StubPage(
        title="Start",
        body_text="body text",
        url="https://example.test/start",
    )
    page.set_scroll_state(scroll_top=0, viewport_height=600, document_height=2000)
    patch_interactions_browser(page)

    async def fake_human_scroll(page_arg: object, direction: str = "down", amount: int | None = None) -> None:
        assert page_arg is page
        assert direction in {"down", "up", "page_down", "page_up", "top", "bottom"}

    monkeypatch.setattr("tools.browser.interactions.human_scroll", fake_human_scroll)

    result = await scroll_page("down")
    assert isinstance(result, str)
    assert "[Page:" in result
    assert "Viewport:" in result
    assert settle_tracker["count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scroll_page_invalid_direction() -> None:
    with pytest.raises(BrowserToolError):
        await scroll_page("")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scroll_budget_warning_after_threshold(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    """After WARN_THRESHOLD scrolls, a warning is injected into the content."""
    _make_scroll_setup(monkeypatch, patch_interactions_browser, settle_tracker)

    # Scroll up to the warning threshold
    result = ""
    for _ in range(_SCROLL_WARN_THRESHOLD):
        result = await scroll_page("down")

    # The last scroll should have a warning
    assert "SCROLL WARNING" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scroll_budget_no_warning_before_threshold(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    """Before the warning threshold, no warning is injected."""
    _make_scroll_setup(monkeypatch, patch_interactions_browser, settle_tracker)

    result = ""
    for _ in range(_SCROLL_WARN_THRESHOLD - 1):
        result = await scroll_page("down")

    assert "SCROLL WARNING" not in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scroll_budget_hard_limit_raises(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    """After HARD_LIMIT scrolls, further scrolls raise BrowserToolError."""
    _make_scroll_setup(monkeypatch, patch_interactions_browser, settle_tracker)

    # Exhaust the budget
    for _ in range(_SCROLL_HARD_LIMIT):
        await scroll_page("down")

    # Next scroll should be refused
    with pytest.raises(BrowserToolError, match="Scroll limit reached"):
        await scroll_page("down")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scroll_budget_resets_on_url_change(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    """Scroll budget resets when the page URL changes."""
    page = StubPage(
        title="Start",
        body_text="body text",
        url="https://example.test/page1",
    )
    page.set_scroll_state(scroll_top=0, viewport_height=600, document_height=2000)
    patch_interactions_browser(page)

    async def fake_human_scroll(page_arg: object, direction: str = "down", amount: int | None = None) -> None:
        pass

    monkeypatch.setattr("tools.browser.interactions.human_scroll", fake_human_scroll)

    # Use up most of the budget
    for _ in range(_SCROLL_HARD_LIMIT - 1):
        await scroll_page("down")

    # Simulate navigation to a new URL
    page.url = "https://example.test/page2"

    # Should work fine — budget is reset for the new URL
    result = await scroll_page("down")
    assert isinstance(result, str)
    # First scroll on new URL, no warning expected
    assert "SCROLL WARNING" not in result
