import pytest

from types import SimpleNamespace

import tools.browser.core.snapshot as snapshot_mod
import tools.browser.core as browser_core
import tools.browser.page as page_mod
from tools.browser import list_anchors, Element


@pytest.mark.asyncio
async def test_filter_contains_case_insensitive(monkeypatch):
    # Prepare fake anchors
    anchors = [
        Element(text="Foo Link", role=None, selector="s1", tag="a", href="https://ex.com/foo"),
        Element(text="Other", role=None, selector="s2", tag="a", href="https://ex.com/other"),
        Element(text="bar", role=None, selector="s3", tag="a", href="https://ex.com/FOO"),
    ]

    async def fake_collect(page):
        return anchors

    async def fake_get_browser():
        class B:
            async def current_page(self):
                return SimpleNamespace(url="http://example")

        return B()

    monkeypatch.setattr(snapshot_mod, "_collect_anchors", fake_collect)
    # page.py imported _collect_anchors at import-time; patch that reference too
    monkeypatch.setattr(page_mod, "_collect_anchors", fake_collect)
    monkeypatch.setattr(browser_core, "get_browser", fake_get_browser)

    res = await list_anchors(contains="foo", limit=10)
    assert isinstance(res, list)
    assert len(res) == 2
    selectors = [e.selector for e in res]
    assert "s1" in selectors and "s3" in selectors


@pytest.mark.asyncio
async def test_cursor_paging_and_limit(monkeypatch):
    anchors = [
        Element(text=f"Link {i}", role=None, selector=f"s{i}", tag="a", href=f"/p{i}")
        for i in range(1, 6)
    ]

    async def fake_collect(page):
        return anchors

    async def fake_get_browser():
        class B:
            async def current_page(self):
                return SimpleNamespace(url="http://example")

        return B()

    monkeypatch.setattr(snapshot_mod, "_collect_anchors", fake_collect)
    monkeypatch.setattr(page_mod, "_collect_anchors", fake_collect)
    monkeypatch.setattr(browser_core, "get_browser", fake_get_browser)

    # after s2, limit 2 -> s3, s4
    res = await list_anchors(after="s2", limit=2)
    assert [e.selector for e in res] == ["s3", "s4"]

    # unknown cursor starts from beginning
    res2 = await list_anchors(after="unknown", limit=2)
    assert [e.selector for e in res2] == ["s1", "s2"]


@pytest.mark.asyncio
async def test_delegates_to_collect_anchors(monkeypatch):
    called = {"v": False}

    async def fake_collect(page):
        called["v"] = True
        return []

    async def fake_get_browser():
        class B:
            async def current_page(self):
                return SimpleNamespace(url="http://example")

        return B()

    monkeypatch.setattr(snapshot_mod, "_collect_anchors", fake_collect)
    monkeypatch.setattr(page_mod, "_collect_anchors", fake_collect)
    monkeypatch.setattr(browser_core, "get_browser", fake_get_browser)

    res = await list_anchors()
    assert called["v"] is True
    assert res == []
