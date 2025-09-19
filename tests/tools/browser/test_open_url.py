import asyncio
from typing import Any

import pytest

from tools.browser import BrowserToolError, PageSnapshot
from tools.browser.open import open_url


class FakeAnchor:
    def __init__(self, text: str, href: str) -> None:
        self._text = text
        self._href = href

    async def inner_text(self) -> str:  # noqa: D401 - simple stub
        return self._text

    async def get_attribute(self, name: str) -> str | None:  # noqa: D401 - simple stub
        if name == "href":
            return self._href
        return None


class FakeField:
    def __init__(self, tag: str, name: str | None = None, input_type: str | None = None) -> None:
        self._tag = tag
        self._name = name
        self._type = input_type

    async def evaluate(self, script: str) -> str:
        # Only supports returning tag name
        return self._tag

    async def get_attribute(self, name: str) -> str | None:
        if name == "name":
            return self._name
        if name == "type":
            return self._type
        return None


class FakeForm:
    def __init__(self, action: str | None, form_id: str | None, fields: list[FakeField]) -> None:
        self._action = action
        self._id = form_id
        self._fields = fields

    async def get_attribute(self, name: str) -> str | None:
        if name == "action":
            return self._action
        if name == "id":
            return self._id
        return None

    async def query_selector_all(self, selector: str) -> list[Any]:
        assert selector == "input, textarea, select"
        return self._fields


class FakeResponse:
    def __init__(self, url: str, status: int) -> None:
        self.url = url
        self.status = status


class FakePage:
    def __init__(
        self,
        title: str,
        body_text: str,
        anchors: list[FakeAnchor],
        forms: list[FakeForm] | None = None,
        final_url: str | None = None,
        status: int = 200,
    ) -> None:
        self._title = title
        self._body_text = body_text
        self._anchors = anchors
        self._forms = forms or []
        self._final_url = final_url
        self._status = status
        self.url = final_url or ""

    async def goto(self, url: str, wait_until: str = "domcontentloaded") -> FakeResponse:
        # Simulate a redirect by returning a different final URL if provided
        final_url = self._final_url or url
        self.url = final_url
        return FakeResponse(final_url, self._status)

    async def title(self) -> str:
        return self._title

    async def inner_text(self, selector: str) -> str:
        assert selector == "body"
        return self._body_text

    async def query_selector_all(self, selector: str) -> list[Any]:
        if selector == "a":
            return self._anchors
        if selector == "form":
            return self._forms
        raise AssertionError(f"Unexpected selector: {selector}")

    async def close(self) -> None:  # noqa: D401 - stub
        return None


class FakeBrowser:
    def __init__(self, page: FakePage) -> None:
        self._page = page

    async def new_page(self) -> FakePage:
        return self._page


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_url_basic(monkeypatch: pytest.MonkeyPatch) -> None:
    """open_url returns title, final url, 500-char snippet, links, forms, status_code."""

    # Build anchors more than 20 to test cap
    anchors = [
        FakeAnchor(text=f"Link {i}", href=f"https://example.com/{i}") for i in range(25)
    ]
    long_body = "x" * 1200
    # Build a login form with username/password
    form = FakeForm(
        action="/login",
        form_id=None,
        fields=[
            FakeField("input", name="username", input_type="text"),
            FakeField("input", name="password", input_type="password"),
            FakeField("input", name=None, input_type="submit"),  # should be ignored
        ],
    )
    page = FakePage(
        title="Example Title",
        body_text=long_body,
        anchors=anchors,
        forms=[form],
        final_url="https://example.com/final",
        status=200,
    )
    fake_browser = FakeBrowser(page)

    # Patch get_browser used inside open_url
    async def fake_get_browser() -> FakeBrowser:
        return fake_browser

    monkeypatch.setattr("tools.browser.open.get_browser", fake_get_browser)

    result: PageSnapshot = await open_url("https://example.com")
    assert result.title == "Example Title"
    assert len(result.snippet) == 500  # clipped to 500
    assert result.url == "https://example.com/final"
    assert result.status_code == 200
    # Only first 20 links
    assert len(result.links) == 20
    # Text trimming to 80 chars is not triggered here but check structure
    assert result.links[0].text.startswith("Link 0")
    assert result.links[0].href == "https://example.com/0"
    # Forms
    assert len(result.forms) == 1
    assert result.forms[0].selector == "form[action='/login']"
    assert result.forms[0].inputs == ["username", "password"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_url_skips_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Links with empty text or href are skipped."""

    anchors = [
        FakeAnchor(text="  ", href="https://x"),
        FakeAnchor(text="Ok", href=""),
        FakeAnchor(text="Good", href="https://ok"),
    ]
    page = FakePage(title="T", body_text="Hello World", anchors=anchors)
    fake_browser = FakeBrowser(page)

    async def fake_get_browser() -> FakeBrowser:
        return fake_browser

    monkeypatch.setattr("tools.browser.open.get_browser", fake_get_browser)

    result = await open_url("https://example.com")
    assert result.title == "T"
    assert result.snippet == "Hello World"
    assert [l.href for l in result.links] == ["https://ok"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_url_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Errors are wrapped in BrowserToolError."""

    class BoomPage(FakePage):
        async def goto(self, url: str, wait_until: str = "domcontentloaded") -> None:  # type: ignore[override]
            raise RuntimeError("boom")

    page = BoomPage(title="T", body_text="", anchors=[])
    fake_browser = FakeBrowser(page)
    async def fake_get_browser() -> FakeBrowser:
        return fake_browser

    monkeypatch.setattr("tools.browser.open.get_browser", fake_get_browser)

    with pytest.raises(BrowserToolError):
        await open_url("https://example.com")
