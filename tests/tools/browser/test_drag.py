from __future__ import annotations

import pytest

from tools.browser import BrowserToolError
from tools.browser.interactions import drag
from tests.tools.browser.support.playwright_stubs import StubLocator, StubPage


async def _human_drag_probe(
    page: StubPage,
    source_locator: StubLocator,
    *,
    target_locator: StubLocator,
) -> None:
    page.drag_calls.append(  # type: ignore[attr-defined]
        {
            "source": source_locator,
            "target": target_locator,
        }
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_drag_with_target_selector(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    page = StubPage(
        title="Drag Playground",
        body_text="Welcome to the drag playground.",
        url="https://example.test/drag",
    )
    page.drag_calls = []  # type: ignore[attr-defined]
    source_locator = page.add_css_locator("#handle")
    target_locator = page.add_css_locator(".drop-zone")

    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_drag", _human_drag_probe)

    result = await drag("#handle", ".drop-zone")
    assert isinstance(result, str)
    assert "[Page:" in result
    assert page.drag_calls == [
        {"source": source_locator, "target": target_locator}
    ]
    assert settle_tracker["count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_drag_with_ref(
    monkeypatch: pytest.MonkeyPatch,
    patch_interactions_browser,
    settle_tracker,
) -> None:
    page = StubPage(
        title="Drag Playground",
        body_text="Welcome to the drag playground.",
        url="https://example.test/drag",
    )
    page.drag_calls = []  # type: ignore[attr-defined]
    source_locator = page.add_ref_locator(1)
    target_locator = page.add_ref_locator(2)

    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_drag", _human_drag_probe)

    result = await drag("1", "2")
    assert "[Page:" in result
    assert page.drag_calls == [
        {"source": source_locator, "target": target_locator}
    ]
    assert settle_tracker["count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_drag_empty_source(
    patch_interactions_browser,
) -> None:
    page = StubPage(
        title="Drag Playground",
        body_text="Welcome to the drag playground.",
        url="https://example.test/drag",
    )
    patch_interactions_browser(page)

    with pytest.raises(BrowserToolError):
        await drag("", "1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_drag_empty_target(
    patch_interactions_browser,
) -> None:
    page = StubPage(
        title="Drag Playground",
        body_text="Welcome to the drag playground.",
        url="https://example.test/drag",
    )
    page.add_ref_locator(1)
    patch_interactions_browser(page)

    with pytest.raises(BrowserToolError):
        await drag("1", "")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_drag_target_not_found(
    patch_interactions_browser,
) -> None:
    page = StubPage(
        title="Drag Playground",
        body_text="Welcome to the drag playground.",
        url="https://example.test/drag",
    )
    page.add_css_locator("#handle")
    patch_interactions_browser(page)

    with pytest.raises(BrowserToolError):
        await drag("#handle", ".missing")
