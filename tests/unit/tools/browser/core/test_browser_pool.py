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

# All get_browser patches target browser.py's namespace since the names
# are bound there at import time, not looked up in sdk.events each call.
_MOD = "tools.browser.core.browser"


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


async def test_agent_gets_ephemeral_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """A sub-agent gets an ephemeral context keyed by agent_id."""
    root = _make_browser()
    ephemeral_ctx = _FakeContext([])
    root._pw_browser.new_context = AsyncMock(return_value=ephemeral_ctx)

    # Sub-agent: depth > 0, so the key is agent_id, not conv_id.
    monkeypatch.setattr(f"{_MOD}.get_current_depth", lambda: 1)
    monkeypatch.setattr(f"{_MOD}.get_conversation_id", lambda: "conv-1")
    monkeypatch.setattr(f"{_MOD}.get_current_agent_id", lambda: "root.1")

    with patch(f"{_MOD}._get_root_browser", new_callable=AsyncMock, return_value=root):
        result = await get_browser()

    assert result is not root
    assert result._context is ephemeral_ctx
    assert "root.1" in _agent_browsers
    assert result._downloads_dir == root._downloads_dir


async def test_agent_reuses_existing_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated get_browser calls from the same agent return the same instance."""
    root = _make_browser()

    monkeypatch.setattr(f"{_MOD}.get_current_depth", lambda: 1)
    monkeypatch.setattr(f"{_MOD}.get_conversation_id", lambda: "conv-1")
    monkeypatch.setattr(f"{_MOD}.get_current_agent_id", lambda: "root.web.1")

    with patch(f"{_MOD}._get_root_browser", new_callable=AsyncMock, return_value=root):
        first = await get_browser()
        second = await get_browser()

    assert first is second
    root._pw_browser.new_context.assert_awaited_once()


async def test_concurrent_agents_get_separate_contexts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two agents with different IDs get separate ephemeral contexts."""
    root = _make_browser()
    root._pw_browser.new_context = AsyncMock(side_effect=[_FakeContext([]), _FakeContext([])])

    monkeypatch.setattr(f"{_MOD}.get_current_depth", lambda: 1)
    monkeypatch.setattr(f"{_MOD}.get_conversation_id", lambda: "conv-1")

    with patch(f"{_MOD}._get_root_browser", new_callable=AsyncMock, return_value=root):
        monkeypatch.setattr(f"{_MOD}.get_current_agent_id", lambda: "task_a.1")
        first = await get_browser()

        monkeypatch.setattr(f"{_MOD}.get_current_agent_id", lambda: "task_b.2")
        second = await get_browser()

    assert first is not second
    assert first._context is not second._context
    assert "task_a.1" in _agent_browsers
    assert "task_b.2" in _agent_browsers


async def test_release_agent_browser_closes_context() -> None:
    """release_agent_browser closes the ephemeral context and removes it from the pool."""
    browser = _make_browser()
    _agent_browsers["agent_x"] = browser

    await release_agent_browser("agent_x")

    assert "agent_x" not in _agent_browsers
    assert browser._closed is True


async def test_release_nonexistent_agent_is_noop() -> None:
    """Releasing a browser for an agent that doesn't exist is a no-op."""
    await release_agent_browser("nonexistent")
    assert len(_agent_browsers) == 0


async def test_root_agent_reuses_conversation_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Subsequent turns of a root agent reuse the conversation-scoped context."""
    root = _make_browser()
    prior_ctx = _FakeContext([_FakePage()])
    prior_browser = Browser(
        context=prior_ctx, extra_headers={}, pw=None, profile_dir=""
    )
    prior_browser._downloads_dir = "/tmp/dl"
    _agent_browsers["conv:abc-123"] = prior_browser

    # Root agent: depth 0, conv_id set — key is "conv:abc-123".
    monkeypatch.setattr(f"{_MOD}.get_current_depth", lambda: 0)
    monkeypatch.setattr(f"{_MOD}.get_conversation_id", lambda: "abc-123")
    monkeypatch.setattr(f"{_MOD}.get_current_agent_id", lambda: "root.computron_kimi.2")

    with patch(f"{_MOD}._get_root_browser", new_callable=AsyncMock, return_value=root):
        result = await get_browser()

    assert result is prior_browser
    assert "conv:abc-123" in _agent_browsers
    root._pw_browser.new_context.assert_not_awaited()


async def test_different_conversation_gets_separate_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """A new conversation creates a fresh browser context, not the prior one."""
    root = _make_browser()
    old_browser = Browser(
        context=_FakeContext([_FakePage()]), extra_headers={}, pw=None, profile_dir=""
    )
    old_browser._downloads_dir = "/tmp/dl"
    _agent_browsers["conv:old-conv"] = old_browser

    monkeypatch.setattr(f"{_MOD}.get_current_depth", lambda: 0)
    monkeypatch.setattr(f"{_MOD}.get_conversation_id", lambda: "new-conv")
    monkeypatch.setattr(f"{_MOD}.get_current_agent_id", lambda: "root.computron_kimi.3")

    with patch(f"{_MOD}._get_root_browser", new_callable=AsyncMock, return_value=root):
        result = await get_browser()

    assert result is not old_browser
    assert "conv:new-conv" in _agent_browsers
    assert "conv:old-conv" in _agent_browsers


async def test_release_conversation_browser_by_key() -> None:
    """release_agent_browser with a conv: key releases the conversation context."""
    browser = _make_browser()
    _agent_browsers["conv:target-conv"] = browser

    await release_agent_browser("conv:target-conv")

    assert "conv:target-conv" not in _agent_browsers
    assert browser._closed is True


async def test_ephemeral_inherits_storage_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ephemeral context is seeded with root's storage state."""
    root = _make_browser()
    root._context._storage = {"cookies": [{"name": "session", "value": "abc"}], "origins": []}
    ephemeral_ctx = _FakeContext([])
    root._pw_browser.new_context = AsyncMock(return_value=ephemeral_ctx)

    monkeypatch.setattr(f"{_MOD}.get_current_depth", lambda: 1)
    monkeypatch.setattr(f"{_MOD}.get_conversation_id", lambda: "conv-1")
    monkeypatch.setattr(f"{_MOD}.get_current_agent_id", lambda: "root.deep.1")

    with patch(f"{_MOD}._get_root_browser", new_callable=AsyncMock, return_value=root):
        await get_browser()

    call_kwargs = root._pw_browser.new_context.call_args[1]
    assert call_kwargs["storage_state"]["cookies"] == [{"name": "session", "value": "abc"}]
