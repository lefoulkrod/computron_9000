"""Shared pytest fixtures for browser tool tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest


class _SimpleBrowser:
    """Minimal browser stub that exposes ``current_page`` for interaction tests."""

    def __init__(self, page: Any) -> None:
        self._page = page

    async def current_page(self) -> Any:
        return self._page


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
    """Intercept ``_wait_for_page_settle`` and record invocation metadata."""

    calls: dict[str, Any] = {"count": 0, "expect_flags": []}

    async def _fake_wait(page: Any, *, expect_navigation: bool, waits: Any) -> None:
        calls["count"] += 1
        calls["expect_flags"].append(expect_navigation)

    monkeypatch.setattr("tools.browser.interactions._wait_for_page_settle", _fake_wait)
    return calls
