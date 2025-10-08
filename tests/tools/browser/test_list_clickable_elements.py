import pytest
from types import SimpleNamespace
from typing import Any

import tools.browser.core.snapshot as snapshot_mod
import tools.browser.core as browser_core
import tools.browser.page as page_mod
from tools.browser import list_clickable_elements, Element


@pytest.mark.asyncio
async def test_filter_contains_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Filtering should match anchors and heuristic clickables (by text or href)."""
    anchors = [
        Element(text="Foo Link", role=None, selector="s1", tag="a", href="https://ex.com/foo"),
        Element(text="Other", role=None, selector="s2", tag="a", href="https://ex.com/other"),
        Element(text="bar", role=None, selector="s3", tag="a", href="https://ex.com/FOO"),
    ]
    clickables = [
        Element(text="Foo Button", role="button", selector="c1", tag="div"),
        Element(text="Baz", role=None, selector="c2", tag="span"),
    ]

    async def fake_collect_anchors(page: Any) -> list[Element]:  # noqa: D401 - simple fake
        return anchors

    async def fake_collect_clickables(page: Any, limit: int | None = None) -> list[Element]:  # noqa: D401 - simple fake
        return clickables

    async def fake_get_browser() -> Any:  # noqa: D401 - simple fake
        class B:
            async def current_page(self) -> SimpleNamespace:
                return SimpleNamespace(url="http://example")

        return B()

    monkeypatch.setattr(snapshot_mod, "_collect_anchors", fake_collect_anchors)
    monkeypatch.setattr(snapshot_mod, "_collect_clickables", fake_collect_clickables)
    # page module imported collectors; patch those too
    monkeypatch.setattr(page_mod, "_collect_anchors", fake_collect_anchors)
    monkeypatch.setattr(page_mod, "_collect_clickables", fake_collect_clickables)
    monkeypatch.setattr(browser_core, "get_browser", fake_get_browser)

    res = await list_clickable_elements(contains="foo", limit=10)
    assert isinstance(res, list)
    selectors = {e.selector for e in res}
    # Should include anchor s1 (text), anchor s3 (href contains FOO), and clickable c1 (text)
    assert selectors == {"s1", "s3", "c1"}


@pytest.mark.asyncio
async def test_cursor_paging_and_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    anchors = [
        Element(text=f"Link {i}", role=None, selector=f"s{i}", tag="a", href=f"/p{i}")
        for i in range(1, 6)
    ]
    clickables = [
        Element(text="Extra 1", role="button", selector="c1", tag="div"),
        Element(text="Extra 2", role=None, selector="c2", tag="span"),
    ]

    async def fake_collect_anchors(page: Any) -> list[Element]:  # noqa: D401
        return anchors

    async def fake_collect_clickables(page: Any, limit: int | None = None) -> list[Element]:  # noqa: D401
        return clickables

    async def fake_get_browser() -> Any:  # noqa: D401
        class B:
            async def current_page(self) -> SimpleNamespace:
                return SimpleNamespace(url="http://example")

        return B()

    monkeypatch.setattr(snapshot_mod, "_collect_anchors", fake_collect_anchors)
    monkeypatch.setattr(snapshot_mod, "_collect_clickables", fake_collect_clickables)
    monkeypatch.setattr(page_mod, "_collect_anchors", fake_collect_anchors)
    monkeypatch.setattr(page_mod, "_collect_clickables", fake_collect_clickables)
    monkeypatch.setattr(browser_core, "get_browser", fake_get_browser)

    # Combined ordering: anchors first then clickables per tool implementation
    res = await list_clickable_elements(after="s2", limit=4)
    # After s2 -> start at s3, include s3, s4, s5, then c1 (limit=4)
    assert [e.selector for e in res] == ["s3", "s4", "s5", "c1"]

    # Unknown cursor -> from beginning
    res2 = await list_clickable_elements(after="unknown", limit=3)
    assert [e.selector for e in res2] == ["s1", "s2", "s3"]


@pytest.mark.asyncio
async def test_delegates_to_collectors(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"anchors": False, "clickables": False}

    async def fake_collect_anchors(page: Any) -> list[Element]:  # noqa: D401
        called["anchors"] = True
        return []

    async def fake_collect_clickables(page: Any, limit: int | None = None) -> list[Element]:  # noqa: D401
        called["clickables"] = True
        return []

    async def fake_get_browser() -> Any:  # noqa: D401
        class B:
            async def current_page(self) -> SimpleNamespace:
                return SimpleNamespace(url="http://example")

        return B()

    monkeypatch.setattr(snapshot_mod, "_collect_anchors", fake_collect_anchors)
    monkeypatch.setattr(snapshot_mod, "_collect_clickables", fake_collect_clickables)
    monkeypatch.setattr(page_mod, "_collect_anchors", fake_collect_anchors)
    monkeypatch.setattr(page_mod, "_collect_clickables", fake_collect_clickables)
    monkeypatch.setattr(browser_core, "get_browser", fake_get_browser)

    res = await list_clickable_elements()
    assert called["anchors"] is True and called["clickables"] is True
    assert res == []
