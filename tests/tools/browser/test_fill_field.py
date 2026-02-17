"""Unit tests for the fill_field browser interaction tool."""

from __future__ import annotations

import pytest

from tools.browser import BrowserToolError
from tools.browser.interactions import InteractionResult, fill_field
from tests.tools.browser.support.playwright_stubs import StubLocator, StubPage


async def _passthrough_human_click(page: object, locator: StubLocator) -> None:
    await locator.click()


async def _passthrough_human_type(page: object, locator: StubLocator, text: str, *, clear_existing: bool = True) -> None:
    if clear_existing:
        await locator.fill("")
    await locator.type(text)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_field_by_css(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    """Types into an input located via CSS selector and returns updated snapshot."""
    page = StubPage(
        title="Initial",
        body_text="Before fill",
        url="https://example.test/form",
    )
    page.add_css_locator(".search-box", tag="input")
    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_click", _passthrough_human_click)
    monkeypatch.setattr("tools.browser.interactions.human_type", _passthrough_human_type)

    result = await fill_field(".search-box", "chips")
    assert isinstance(result, InteractionResult)
    assert result.page_changed is False
    assert result.reason == "no-change"
    assert result.page_view is None
    assert getattr(page, "_body_text", "").startswith("Filled value: chips")
    assert settle_tracker["count"] == 1
    assert settle_tracker["expect_flags"] == [False]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_field_by_visible_text(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    """Falls back to exact visible text to locate the input field."""
    page = StubPage(
        title="Initial",
        body_text="Before fill",
        url="https://example.test/form",
    )
    page.add_text_locator("Email", tag="input")
    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_click", _passthrough_human_click)
    monkeypatch.setattr("tools.browser.interactions.human_type", _passthrough_human_type)

    result = await fill_field("Email", "user@example.com")
    assert result.page_changed is False
    assert result.reason == "no-change"
    assert result.page_view is None
    assert "user@example.com" in getattr(page, "_body_text", "")
    assert settle_tracker["count"] == 1
    assert settle_tracker["expect_flags"] == [False]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_field_rejects_checkbox(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
) -> None:
    """Rejects unsupported input types such as checkbox."""
    page = StubPage(
        title="Initial",
        body_text="Before fill",
        url="https://example.test/form",
    )
    page.add_css_locator("#agree", tag="input", input_type="checkbox")
    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_click", _passthrough_human_click)
    monkeypatch.setattr("tools.browser.interactions.human_type", _passthrough_human_type)

    with pytest.raises(BrowserToolError):
        await fill_field("#agree", True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_field_requires_non_empty_selector(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
) -> None:
    """Rejects whitespace-only selectors."""
    page = StubPage(
        title="Initial",
        body_text="Before fill",
        url="https://example.test/form",
    )
    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_click", _passthrough_human_click)
    monkeypatch.setattr("tools.browser.interactions.human_type", _passthrough_human_type)

    with pytest.raises(BrowserToolError):
        await fill_field("   ", "value")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_field_select_element(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
) -> None:
    """Raising error for select elements which are no longer supported."""
    page = StubPage(
        title="Initial",
        body_text="Before fill",
        url="https://example.test/form",
    )
    page.add_css_locator("#country", tag="select")
    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_click", _passthrough_human_click)
    monkeypatch.setattr("tools.browser.interactions.human_type", _passthrough_human_type)

    with pytest.raises(BrowserToolError):
        await fill_field("#country", "us")
