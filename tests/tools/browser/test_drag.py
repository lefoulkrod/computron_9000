from __future__ import annotations

import pytest

from tools.browser import BrowserToolError, PageSnapshot
from tools.browser.interactions import drag
from tests.tools.browser.support.playwright_stubs import StubLocator, StubPage


async def _human_drag_probe(
    page: StubPage,
    source_locator: StubLocator,
    *,
    target_locator: StubLocator | None = None,
    offset: tuple[float, float] | None = None,
) -> None:
    page.drag_calls.append(  # type: ignore[attr-defined]
        {
            "source": source_locator,
            "target": target_locator,
            "offset": offset,
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

    snapshot = await drag("#handle", target=".drop-zone")
    assert isinstance(snapshot, PageSnapshot)
    assert page.drag_calls == [
        {"source": source_locator, "target": target_locator, "offset": None}
    ]
    assert settle_tracker["count"] == 1
    assert settle_tracker["expect_flags"] == [False]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_drag_with_offset(
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
    source_locator = page.add_text_locator("Drag me")

    patch_interactions_browser(page)
    monkeypatch.setattr("tools.browser.interactions.human_drag", _human_drag_probe)

    snapshot = await drag("Drag me", offset=(25, -10))
    assert isinstance(snapshot, PageSnapshot)
    assert page.drag_calls == [
        {"source": source_locator, "target": None, "offset": (25.0, -10.0)}
    ]
    assert settle_tracker["count"] == 1
    assert settle_tracker["expect_flags"] == [False]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_drag_requires_destination(
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
        await drag("#handle")

    with pytest.raises(BrowserToolError):
        await drag("#handle", target=".missing", offset=(5, 5))


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
        await drag("#handle", target=".missing")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_drag_invalid_offset_type(
    patch_interactions_browser,
) -> None:
    page = StubPage(
        title="Drag Playground",
        body_text="Welcome to the drag playground.",
        url="https://example.test/drag",
    )
    page.add_text_locator("Drag me")
    patch_interactions_browser(page)

    with pytest.raises(BrowserToolError):
        await drag("Drag me", offset=("bad", 5))  # type: ignore[arg-type]
