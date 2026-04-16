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
    """Create a Browser with a fake context and a mock pw_browser for sub-agent contexts."""
    ctx = _FakeContext([_FakePage()])
    # Mock pw_browser so agents can call root._pw_browser.new_context()
    mock_pw_browser = MagicMock()
    mock_pw_browser.new_context = AsyncMock(return_value=_FakeContext([]))
    b = Browser(context=ctx, extra_headers={"Accept-Language": "en"}, pw_browser=mock_pw_browser, **kwargs)  # type: ignore[arg-type]
    b._downloads_dir = "/tmp/dl"
    return b


@pytest.fixture(autouse=True)
def _clean_pool():
    """Ensure the global pool is clean."""
    _agent_browsers.clear()
    yield
    _agent_browsers.clear()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_gets_ephemeral_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every agent gets an ephemeral context, never the root browser directly."""
    root = _make_browser()
    ephemeral_ctx = _FakeContext([])
    root._pw_browser.new_context = AsyncMock(return_value=ephemeral_ctx)

    monkeypatch.setattr("sdk.events.get_current_agent_id", lambda: "root.1")

    with patch("tools.browser.core.browser._get_root_browser", new_callable=AsyncMock, return_value=root):
        result = await get_browser()

    assert result is not root
    assert result._context is ephemeral_ctx
    assert "root.1" in _agent_browsers
    assert result._downloads_dir == root._downloads_dir


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_reuses_existing_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated get_browser calls from the same agent return the same instance."""
    root = _make_browser()

    monkeypatch.setattr("sdk.events.get_current_agent_id", lambda: "root.web.1")

    with patch("tools.browser.core.browser._get_root_browser", new_callable=AsyncMock, return_value=root):
        first = await get_browser()
        second = await get_browser()

    assert first is second
    root._pw_browser.new_context.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_concurrent_agents_get_separate_contexts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two agents with different IDs get separate ephemeral contexts."""
    root = _make_browser()
    # Return a fresh context each time
    root._pw_browser.new_context = AsyncMock(side_effect=[_FakeContext([]), _FakeContext([])])

    with patch("tools.browser.core.browser._get_root_browser", new_callable=AsyncMock, return_value=root):
        monkeypatch.setattr("sdk.events.get_current_agent_id", lambda: "task_a.1")
        first = await get_browser()

        monkeypatch.setattr("sdk.events.get_current_agent_id", lambda: "task_b.2")
        second = await get_browser()

    assert first is not second
    assert first._context is not second._context
    assert "task_a.1" in _agent_browsers
    assert "task_b.2" in _agent_browsers


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
    ephemeral_ctx = _FakeContext([])
    root._pw_browser.new_context = AsyncMock(return_value=ephemeral_ctx)

    monkeypatch.setattr("sdk.events.get_current_agent_id", lambda: "root.deep.1")

    with patch("tools.browser.core.browser._get_root_browser", new_callable=AsyncMock, return_value=root):
        await get_browser()

    call_kwargs = root._pw_browser.new_context.call_args[1]
    assert call_kwargs["storage_state"]["cookies"] == [{"name": "session", "value": "abc"}]
