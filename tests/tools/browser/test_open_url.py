import pytest

from tools.browser import BrowserToolError, PageSnapshot
from tools.browser.page import open_url
from tests.tools.browser.support.playwright_stubs import (
    StubAnchor,
    StubBrowser,
    StubField,
    StubForm,
    StubPage,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_url_basic(monkeypatch: pytest.MonkeyPatch) -> None:
    """open_url returns title, final url, 500-char snippet, links, forms, status_code."""

    # Build anchors more than 20 to test cap
    anchors = [
        StubAnchor(text=f"Link {i}", href=f"https://example.com/{i}") for i in range(25)
    ]
    long_body = "x" * 1200
    # Build a login form with username/password
    form = StubForm(
        action="/login",
        form_id=None,
        fields=[
            StubField("input", name="username", input_type="text"),
            StubField("input", name="password", input_type="password"),
            StubField("input", name=None, input_type="submit"),  # should be ignored
        ],
    )
    page = StubPage(
        title="Example Title",
        body_text=long_body,
        anchors=anchors,
        forms=[form],
        final_url="https://example.com/final",
        status=200,
    )
    fake_browser = StubBrowser(page)

    # Patch get_browser used inside open_url
    async def fake_get_browser() -> StubBrowser:
        return fake_browser

    # Patch core.get_browser so open_url uses our fake browser
    monkeypatch.setattr("tools.browser.core.get_browser", fake_get_browser)

    result: PageSnapshot = await open_url("https://example.com")
    assert result.title == "Example Title"
    assert len(result.snippet) == 500  # clipped to 500
    assert result.url == "https://example.com/final"
    assert result.status_code == 200
    # Only first 20 links
    # Elements: first 20 anchors plus the form (order: anchors then forms)
    anchor_elements = [e for e in result.elements if e.tag == "a"]
    form_elements = [e for e in result.elements if e.tag == "form"]
    assert len(anchor_elements) == 20
    assert anchor_elements[0].text.startswith("Link 0")
    assert anchor_elements[0].href == "https://example.com/0"
    assert len(form_elements) == 1
    assert form_elements[0].action == "/login"
    assert form_elements[0].fields is not None
    assert [f.name for f in form_elements[0].fields] == ["username", "password"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_url_skips_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Links with empty text or href are skipped."""

    anchors = [
        StubAnchor(text="  ", href="https://x"),
        StubAnchor(text="Ok", href=""),
        StubAnchor(text="Good", href="https://ok"),
    ]
    page = StubPage(title="T", body_text="Hello World", anchors=anchors)
    fake_browser = StubBrowser(page)

    async def fake_get_browser() -> StubBrowser:
        return fake_browser

    monkeypatch.setattr("tools.browser.core.get_browser", fake_get_browser)

    result = await open_url("https://example.com")
    assert result.title == "T"
    assert result.snippet == "Hello World"
    anchor_elements = [e for e in result.elements if e.tag == "a"]
    assert [e.href for e in anchor_elements] == ["https://ok"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_url_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Errors are wrapped in BrowserToolError."""

    class BoomPage(StubPage):
        async def goto(self, url: str, wait_until: str = "domcontentloaded") -> None:  # type: ignore[override]
            raise RuntimeError("boom")

    page = BoomPage(title="T", body_text="", anchors=[])
    fake_browser = StubBrowser(page)

    async def fake_get_browser() -> StubBrowser:
        return fake_browser

    monkeypatch.setattr("tools.browser.core.get_browser", fake_get_browser)

    with pytest.raises(BrowserToolError):
        await open_url("https://example.com")
