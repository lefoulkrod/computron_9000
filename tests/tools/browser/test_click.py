from __future__ import annotations

import asyncio
import typing
import pytest

from tools.browser import BrowserToolError, PageSnapshot
from tools.browser.interactions import click


async def _human_click_passthrough(page: object, locator: FakeLocator) -> None:
    await locator.click()


class FakeResponse:
    def __init__(self, url: str, status: int) -> None:
        self.url = url
        self.status = status


class FakeLocator:
    def __init__(self, page: "FakePage", *, navigates_to: str | None = None) -> None:  # noqa: D401
        self._page = page
        self._navigates_to = navigates_to
        self._clicked = False

    async def count(self) -> int:  # noqa: D401 - simple stub
        # If it has a navigation target we consider it present.
        return 1 if self._navigates_to or self in self._page._all_locators else 0

    async def click(self) -> None:  # noqa: D401 - simple stub
        self._clicked = True
        if self._navigates_to:
            # Simulate navigation by changing page state.
            self._page.url = self._navigates_to
            self._page._title = "After Click"
            self._page._body_text = "Arrived after navigation"
            # Signal navigation to any wait_for_event watchers in tests
            if hasattr(self._page, "_nav_event"):
                self._page._nav_event.set()

    @property
    def first(self) -> "FakeLocator":  # noqa: D401 - Playwright API parity
        return self


class FakeNavContext:
    def __init__(self, page: "FakePage") -> None:  # noqa: D401 - stub
        self._page = page

    async def __aenter__(self) -> "FakeNavContext":  # noqa: D401 - stub
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> None:  # noqa: D401 - stub
        return None

    @property
    def value(self) -> object:  # noqa: D401 - mimic Playwright property returning awaitable
        async def _get() -> FakeResponse:
            return FakeResponse(self._page.url, 200)

        return typing.cast(object, _get())


class FakePage:
    def __init__(self) -> None:  # noqa: D401
        self._title = "Initial"
        self._body_text = "Before click"
        self.url = "https://example.test/start"
        # Maps
        self._text_locators: dict[str, FakeLocator] = {}
        self._css_locators: dict[str, FakeLocator] = {}
        self._anchors: list[object] = []  # no links needed for tests
        self._forms: list[object] = []
        self._all_locators: set[FakeLocator] = set()
        # Minimal primitives to emulate Playwright event/load_state APIs for tests
        self._nav_event = asyncio.Event()
        self.main_frame = object()

    # Playwright subset used by snapshot builder
    async def title(self) -> str:  # noqa: D401 - stub
        return self._title

    async def inner_text(self, selector: str) -> str:  # noqa: D401 - stub
        assert selector == "body"
        return self._body_text

    async def query_selector_all(self, selector: str) -> list[object]:  # noqa: D401 - stub
        if selector == "a":
            return self._anchors
        if selector == "form":
            return self._forms
        return []

    # Interaction helpers
    def add_text_element(self, text: str, navigates_to: str | None = None) -> None:
        loc = FakeLocator(self, navigates_to=navigates_to)
        self._text_locators[text] = loc
        self._all_locators.add(loc)

    def add_css_element(self, selector: str, navigates_to: str | None = None) -> None:
        loc = FakeLocator(self, navigates_to=navigates_to)
        self._css_locators[selector] = loc
        self._all_locators.add(loc)

    async def wait_for_event(self, name: str, *, predicate: object | None = None) -> object | None:  # pragma: no cover - test helper
        # Only support framenavigated predicate for test doubles
        if name != "framenavigated":
            raise RuntimeError("Unsupported event in FakePage")
        # Wait until navigation is signaled by the locator click behavior
        await self._nav_event.wait()
        # Reset for future navigations
        self._nav_event.clear()
        return None

    async def wait_for_load_state(self, state: str, timeout: int | None = None) -> None:  # pragma: no cover - test helper
        # For tests, domcontentloaded can be considered immediate after navigation
        # If the page hasn't navigated, return immediately (no-op)
        return None

    def get_by_text(self, text: str, exact: bool = True) -> FakeLocator:  # noqa: D401 - stub
        return self._text_locators.get(text, FakeLocator(self))

    def locator(self, selector: str) -> FakeLocator:  # noqa: D401 - stub
        return self._css_locators.get(selector, FakeLocator(self))

    def expect_navigation(self, *args: object, **kwargs: object) -> FakeNavContext:  # noqa: D401 - stub
        return FakeNavContext(self)


class FakeBrowser:
    def __init__(self, page: FakePage) -> None:  # noqa: D401
        self._page = page

    async def current_page(self) -> FakePage:  # noqa: D401 - stub
        return self._page


@pytest.mark.unit
@pytest.mark.asyncio
async def test_click_by_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clicking by visible text performs navigation and returns a snapshot."""

    page = FakePage()
    page.add_text_element("Continue", navigates_to="https://example.test/after")
    fake_browser = FakeBrowser(page)

    async def fake_get_browser() -> FakeBrowser:  # noqa: D401 - stub
        return fake_browser

    monkeypatch.setattr("tools.browser.interactions.get_browser", fake_get_browser)
    monkeypatch.setattr("tools.browser.interactions.human_click", _human_click_passthrough)
    called = {"count": 0}

    async def fake_wait(page: object, *, expect_navigation: bool, waits: object) -> None:
        called["count"] += 1

    monkeypatch.setattr("tools.browser.interactions._wait_for_page_settle", fake_wait)

    snap: PageSnapshot = await click("Continue")
    assert snap.url == "https://example.test/after"
    assert snap.title == "After Click"
    assert "Arrived" in snap.snippet


@pytest.mark.unit
@pytest.mark.asyncio
async def test_click_by_css_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    """Falls back to CSS selector when no text match exists."""

    page = FakePage()
    page.add_css_element(".cta", navigates_to="https://example.test/cta")
    fake_browser = FakeBrowser(page)

    async def fake_get_browser() -> FakeBrowser:  # noqa: D401 - stub
        return fake_browser

    monkeypatch.setattr("tools.browser.interactions.get_browser", fake_get_browser)
    monkeypatch.setattr("tools.browser.interactions.human_click", _human_click_passthrough)

    called = {"count": 0}

    async def fake_wait(page: object, *, expect_navigation: bool, waits: object) -> None:
        called["count"] += 1

    monkeypatch.setattr("tools.browser.interactions._wait_for_page_settle", fake_wait)

    snap = await click(".cta")
    assert snap.url.endswith("/cta")
    assert snap.title == "After Click"
    assert called["count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_click_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raises BrowserToolError when element can't be located."""

    page = FakePage()
    fake_browser = FakeBrowser(page)

    async def fake_get_browser() -> FakeBrowser:  # noqa: D401 - stub
        return fake_browser

    monkeypatch.setattr("tools.browser.interactions.get_browser", fake_get_browser)
    monkeypatch.setattr("tools.browser.interactions.human_click", _human_click_passthrough)

    with pytest.raises(BrowserToolError):
        await click("Does Not Exist")
