"""Tests for the browser context pool (copy-on-create isolation)."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.browser.core.browser import (
    Browser,
    _agent_browsers,
    get_browser,
    release_agent_browser,
)


class _FakePage:
    def __init__(self, closed: bool = False) -> None:
        self._closed = closed

    def is_closed(self) -> bool:
        return self._closed

    def on(self, event: str, callback: Any) -> None:
        pass

    async def close(self) -> None:
        self._closed = True


class _FakeContext:
    """Minimal stub for BrowserContext used by Browser."""

    def __init__(self, pages: list[_FakePage] | None = None) -> None:
        self.pages = pages or []
        self.browser = MagicMock()
        self._storage = {"cookies": [], "origins": []}
        self._closed = False

    def on(self, event: str, callback: Any) -> None:
        pass

    def remove_listener(self, event: str, callback: Any) -> None:
        pass

    async def new_page(self) -> _FakePage:
        page = _FakePage()
        self.pages.append(page)
        return page

    async def storage_state(self) -> dict[str, Any]:
        return dict(self._storage)

    async def close(self) -> None:
        self._closed = True

    async def set_extra_http_headers(self, headers: dict[str, str]) -> None:
        pass

    async def add_init_script(self, script: str) -> None:
        pass


def _make_browser(**kwargs: Any) -> Browser:
    ctx = _FakeContext([_FakePage()])
    b = Browser(context=ctx, extra_headers={"Accept-Language": "en"}, **kwargs)
    b._downloads_dir = "/tmp/dl"
    b._container_dir = "/home/computron"
    return b


@pytest.fixture(autouse=True)
def _clean_pool():
    """Ensure the global pool is clean before and after each test."""
    _agent_browsers.clear()
    yield
    _agent_browsers.clear()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_root_agent_gets_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    """Depth 0 returns the persistent root browser."""
    root = _make_browser()
    monkeypatch.setattr("sdk.events.get_current_depth", lambda: 0)
    monkeypatch.setattr("sdk.events.get_current_agent_id", lambda: "root")

    with patch("tools.browser.core.browser._get_root_browser", new_callable=AsyncMock, return_value=root):
        result = await get_browser()

    assert result is root
    assert len(_agent_browsers) == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sub_agent_gets_ephemeral_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sub-agents (depth > 0) get an ephemeral context, not the root singleton."""
    root = _make_browser()
    # Make the root context's browser.new_context return a new fake context
    new_ctx = _FakeContext([])
    root._context.browser.new_context = AsyncMock(return_value=new_ctx)

    monkeypatch.setattr("sdk.events.get_current_depth", lambda: 1)
    monkeypatch.setattr("sdk.events.get_current_agent_id", lambda: "root.browser_agent.1")

    with patch("tools.browser.core.browser._get_root_browser", new_callable=AsyncMock, return_value=root):
        result = await get_browser()

    assert result is not root
    assert result._context is new_ctx
    assert "root.browser_agent.1" in _agent_browsers
    # Inherits download dirs from root
    assert result._downloads_dir == root._downloads_dir
    assert result._container_dir == root._container_dir


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sub_agent_reuses_existing_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated get_browser calls from the same sub-agent return the same instance."""
    root = _make_browser()
    new_ctx = _FakeContext([])
    root._context.browser.new_context = AsyncMock(return_value=new_ctx)

    monkeypatch.setattr("sdk.events.get_current_depth", lambda: 1)
    monkeypatch.setattr("sdk.events.get_current_agent_id", lambda: "root.web.1")

    with patch("tools.browser.core.browser._get_root_browser", new_callable=AsyncMock, return_value=root):
        first = await get_browser()
        second = await get_browser()

    assert first is second
    # new_context called only once
    root._context.browser.new_context.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_release_agent_browser_closes_context() -> None:
    """release_agent_browser closes the ephemeral context and removes it from the pool."""
    browser = _make_browser()
    _agent_browsers["agent_x"] = browser

    await release_agent_browser("agent_x")

    assert "agent_x" not in _agent_browsers
    assert browser._closed is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_release_nonexistent_agent_is_noop() -> None:
    """Releasing a browser for an agent that doesn't exist is a no-op."""
    await release_agent_browser("nonexistent")
    assert len(_agent_browsers) == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ephemeral_inherits_storage_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ephemeral context is seeded with root's storage state."""
    root = _make_browser()
    root._context._storage = {"cookies": [{"name": "session", "value": "abc"}], "origins": []}
    new_ctx = _FakeContext([])
    root._context.browser.new_context = AsyncMock(return_value=new_ctx)

    monkeypatch.setattr("sdk.events.get_current_depth", lambda: 2)
    monkeypatch.setattr("sdk.events.get_current_agent_id", lambda: "root.deep.1")

    with patch("tools.browser.core.browser._get_root_browser", new_callable=AsyncMock, return_value=root):
        await get_browser()

    # Verify storage_state was passed to new_context
    call_kwargs = root._context.browser.new_context.call_args[1]
    assert call_kwargs["storage_state"]["cookies"] == [{"name": "session", "value": "abc"}]
