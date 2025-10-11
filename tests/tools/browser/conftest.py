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
        self._last_metadata: dict[str, Any] | None = None

    async def current_page(self) -> Any:
        return self._page

    async def perform_interaction(
        self,
        page: Any,
        action: Callable[[], Awaitable[Any]],
    ) -> BrowserInteractionResult:
        """Mimic Browser.perform for tests without requiring Playwright."""
        initial_url = getattr(page, "url", "")
        await action()
        final_url = getattr(page, "url", "")
        navigation = bool(initial_url and final_url and final_url != initial_url)
        page_changed = navigation
        reason = "hard-navigation" if navigation else "none"

        from tools.browser.core.waits import wait_for_page_settle as settle_helper
        waits = load_config().tools.browser.waits
        await settle_helper(page, expect_navigation=navigation, waits=waits)

        metadata = BrowserInteractionResult(
            navigation=navigation,
            page_changed=page_changed,
            reason=reason,
            navigation_response=None,
        )
        self._last_metadata = metadata.model_dump()
        return metadata


@pytest.fixture
def patch_interactions_browser(monkeypatch: pytest.MonkeyPatch) -> Callable[[Any], _SimpleBrowser]:
    """Patch ``tools.browser.interactions.get_browser`` to return a stub browser.

    Returns a callable so individual tests can supply their own fake page objects while
    reusing the same patching logic.
    """

    def _apply(page: Any) -> _SimpleBrowser:
        browser = _SimpleBrowser(page)

        async def _get_browser() -> _SimpleBrowser:
            return browser

        monkeypatch.setattr("tools.browser.interactions.get_browser", _get_browser)
        return browser

    return _apply


@pytest.fixture
def settle_tracker(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Intercept ``wait_for_page_settle`` and record invocation metadata."""

    calls: dict[str, Any] = {"count": 0, "expect_flags": []}

    async def _fake_wait(page: Any, *, expect_navigation: bool, waits: Any) -> None:
        calls["count"] += 1
        calls["expect_flags"].append(expect_navigation)

    monkeypatch.setattr("tools.browser.core.waits.wait_for_page_settle", _fake_wait)
    return calls
