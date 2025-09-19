import pytest

from tools.browser import BrowserToolError, PageSnapshot
from tools.browser.interactions import click


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
    def value(self):  # noqa: D401 - mimic Playwright property returning awaitable
        async def _get() -> FakeResponse:
            return FakeResponse(self._page.url, 200)

        return _get()


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

    snap = await click(".cta")
    assert snap.url.endswith("/cta")
    assert snap.title == "After Click"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_click_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raises BrowserToolError when element can't be located."""

    page = FakePage()
    fake_browser = FakeBrowser(page)

    async def fake_get_browser() -> FakeBrowser:  # noqa: D401 - stub
        return fake_browser

    monkeypatch.setattr("tools.browser.interactions.get_browser", fake_get_browser)

    with pytest.raises(BrowserToolError):
        await click("Does Not Exist")
