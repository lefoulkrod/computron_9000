"""Shared pytest fixtures for browser tool tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Awaitable

import pytest

from config import load_config
from tools.browser.core.browser import BrowserInteractionResult


class _SimpleBrowser:
    """Minimal browser stub that exposes ``current_page`` for interaction tests."""

    def __init__(self, page: Any) -> None:
        self._page = page
        self._active_frame: Any | None = None
        self._last_metadata: dict[str, Any] | None = None

    async def current_page(self) -> Any:
        return self._page

    async def active_frame(self) -> Any:
        if self._active_frame is not None:
            if hasattr(self._active_frame, "is_detached") and self._active_frame.is_detached():
                self._active_frame = None
            else:
                return self._active_frame
        return self._page

    async def active_view(self) -> Any:
        from tools.browser.core.browser import ActiveView
        frame = await self.active_frame()
        page = await self.current_page()
        try:
            title = await page.title()
        except Exception:
            title = "Test Page"
        return ActiveView(frame=frame, title=title, url=page.url)

    def clear_active_frame(self) -> None:
        self._active_frame = None

    async def navigate_back(self) -> BrowserInteractionResult:
        page = await self.current_page()

        async def _back() -> None:
            await page.go_back(wait_until="domcontentloaded")

        return await self.perform_interaction(_back)

    async def perform_interaction(
        self,
        action: Callable[[], Awaitable[Any]],
    ) -> BrowserInteractionResult:
        """Mimic Browser.perform for tests without requiring Playwright."""
        page = await self.current_page()
        await action()

        from tools.browser.core.waits import wait_for_page_settle as settle_helper
        waits = load_config().tools.browser.waits
        await settle_helper(page, waits=waits)

        metadata = BrowserInteractionResult(
            navigation_response=None,
        )
        self._last_metadata = metadata.model_dump()
        return metadata


class _NoSnapshotPage:
    """Page stub with no screenshot capability, so the events decorator exits early."""


class _NoSnapshotBrowser:
    """Browser stub that returns a page with no screenshot method."""

    async def current_page(self) -> _NoSnapshotPage:
        return _NoSnapshotPage()


@pytest.fixture(autouse=True)
def _reset_scroll_budget() -> None:
    """Reset scroll budget tracking between tests."""
    from tools.browser.interactions import _scroll_count_var, _scroll_url_var

    _scroll_count_var.set(0)
    _scroll_url_var.set("")


@pytest.fixture
def patch_interactions_browser(monkeypatch: pytest.MonkeyPatch) -> Callable[[Any], _SimpleBrowser]:
    """Patch ``tools.browser.interactions.get_browser`` to return a stub browser.

    Also patches ``tools.browser.events.get_browser`` so the
    ``emit_screenshot_after`` decorator does not try to launch a
    real Playwright browser when capturing post-interaction snapshots.

    Returns a callable so individual tests can supply their own fake page objects while
    reusing the same patching logic.
    """
    _no_snapshot_browser = _NoSnapshotBrowser()

    async def _events_get_browser() -> _NoSnapshotBrowser:
        return _no_snapshot_browser

    monkeypatch.setattr("tools.browser.events.get_browser", _events_get_browser)

    def _apply(page: Any) -> _SimpleBrowser:
        browser = _SimpleBrowser(page)

        async def _get_browser() -> _SimpleBrowser:
            return browser

        async def _get_active_view(tool_name: str) -> tuple[_SimpleBrowser, Any]:
            from tools.browser.core.exceptions import BrowserToolError
            view = await browser.active_view()
            if view.url in {"", "about:blank"}:
                raise BrowserToolError("Navigate to a page first.", tool=tool_name)
            return browser, view

        monkeypatch.setattr("tools.browser.interactions.get_browser", _get_browser)
        monkeypatch.setattr("tools.browser.interactions.get_active_view", _get_active_view)
        return browser

    return _apply


@pytest.fixture
def settle_tracker(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Intercept ``wait_for_page_settle`` and record invocation metadata."""

    calls: dict[str, Any] = {"count": 0}

    async def _fake_wait(page: Any, *, waits: Any) -> Any:
        from tools.browser.core.waits import SettleTimings

        calls["count"] += 1
        return SettleTimings()

    monkeypatch.setattr("tools.browser.core.waits.wait_for_page_settle", _fake_wait)
    return calls
