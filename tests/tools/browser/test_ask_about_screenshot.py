from __future__ import annotations

import base64
from types import SimpleNamespace
import importlib

import pytest

from tools.browser import BrowserToolError
from tools.browser.ask_about_screenshot import ask_about_screenshot


class FakeLocator:
    def __init__(self, screenshot_bytes: bytes, exists: bool = True) -> None:
        self._screenshot_bytes = screenshot_bytes
        self._exists = exists
        self.first = self

    async def count(self) -> int:
        return 1 if self._exists else 0

    async def screenshot(self, *, type: str = "png") -> bytes:  # noqa: A003
        assert type == "png"
        if not self._exists:
            raise AssertionError("Should not capture screenshot when locator does not exist")
        return self._screenshot_bytes


class FakePage:
    def __init__(
        self,
        screenshot_bytes: bytes,
        *,
        url: str = "https://example.com",
        locator_map: dict[str, FakeLocator] | None = None,
    ) -> None:
        self._screenshot_bytes = screenshot_bytes
        self._locator_map = locator_map or {}
        self.url = url

    async def screenshot(self, *, full_page: bool = False, type: str = "png") -> bytes:  # noqa: A003
        assert type == "png"
        if full_page:
            return self._screenshot_bytes
        # viewport screenshots reuse same bytes in this fake
        return self._screenshot_bytes

    def locator(self, selector: str) -> FakeLocator:
        return self._locator_map.get(selector, FakeLocator(b"", exists=False))

    def get_by_text(self, value: str, exact: bool = True) -> FakeLocator:
        # Screenshot tool no longer resolves via text; return a non-existing locator.
        return FakeLocator(b"", exists=False)


class FakeBrowser:
    def __init__(self, page: FakePage) -> None:
        self._page = page

    async def current_page(self) -> FakePage:
        return self._page


class FakeClient:
    last_kwargs: dict[str, object] | None = None
    last_host: str | None = None

    def __init__(self, host: str | None = None) -> None:
        FakeClient.last_host = host

    async def generate(self, **kwargs: object) -> SimpleNamespace:
        FakeClient.last_kwargs = kwargs
        return SimpleNamespace(response="Mock answer")


class FakeModel:
    model = "vision-model"
    options = {"temperature": 0.0}
    think = False


class FakeConfig:
    class _LLM:
        host = "http://fake-host"

    llm = _LLM()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ask_about_screenshot_success(monkeypatch: pytest.MonkeyPatch) -> None:
    page = FakePage(b"fake-image-bytes")
    browser = FakeBrowser(page)

    async def fake_get_browser() -> FakeBrowser:
        return browser

    fake_model = FakeModel()

    FakeClient.last_kwargs = None
    FakeClient.last_host = None

    module = importlib.import_module("tools.browser.ask_about_screenshot")

    monkeypatch.setattr(module, "get_browser", fake_get_browser)
    monkeypatch.setattr(module, "AsyncClient", FakeClient)
    monkeypatch.setattr(module, "get_model_by_name", lambda name: fake_model)
    monkeypatch.setattr(module, "load_config", lambda: FakeConfig())

    answer = await ask_about_screenshot("What is in the header?")

    assert answer == "Mock answer"
    assert FakeClient.last_host == FakeConfig.llm.host

    assert FakeClient.last_kwargs is not None
    assert FakeClient.last_kwargs["prompt"] == "What is in the header?"
    assert FakeClient.last_kwargs["model"] == fake_model.model
    images = FakeClient.last_kwargs["images"]
    assert isinstance(images, list)
    assert len(images) == 1
    encoded = base64.b64encode(b"fake-image-bytes").decode("ascii")
    assert getattr(images[0], "value", None) == encoded


## Additional selector handling tests appended after core tests


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ask_about_screenshot_rejects_blank_prompt() -> None:
    with pytest.raises(BrowserToolError):
        await ask_about_screenshot("   ")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ask_about_screenshot_requires_navigation(monkeypatch: pytest.MonkeyPatch) -> None:
    page = FakePage(b"img", url="about:blank")
    browser = FakeBrowser(page)

    async def fake_get_browser() -> FakeBrowser:
        return browser

    module = importlib.import_module("tools.browser.ask_about_screenshot")

    monkeypatch.setattr(module, "get_browser", fake_get_browser)

    with pytest.raises(BrowserToolError):
        await ask_about_screenshot("Describe the page")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ask_about_screenshot_selector_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    locator = FakeLocator(b"element-bytes")
    page = FakePage(b"page-bytes", locator_map={"#hero": locator})
    browser = FakeBrowser(page)

    async def fake_get_browser() -> FakeBrowser:
        return browser

    fake_model = FakeModel()

    FakeClient.last_kwargs = None
    FakeClient.last_host = None

    module = importlib.import_module("tools.browser.ask_about_screenshot")

    monkeypatch.setattr(module, "get_browser", fake_get_browser)
    monkeypatch.setattr(module, "AsyncClient", FakeClient)
    monkeypatch.setattr(module, "get_model_by_name", lambda name: fake_model)
    monkeypatch.setattr(module, "load_config", lambda: FakeConfig())

    answer = await ask_about_screenshot("Describe the hero", mode="selector", selector="#hero")

    assert answer == "Mock answer"
    assert FakeClient.last_kwargs is not None
    assert "images" in FakeClient.last_kwargs
    assert len(FakeClient.last_kwargs["images"]) > 0
    assert getattr(FakeClient.last_kwargs["images"][0], "value", None) == base64.b64encode(
        b"element-bytes"
    ).decode("ascii")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_selector_requires_non_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    page = FakePage(b"page")
    browser = FakeBrowser(page)

    async def fake_get_browser() -> FakeBrowser:
        return browser

    module = importlib.import_module("tools.browser.ask_about_screenshot")
    monkeypatch.setattr(module, "get_browser", fake_get_browser)

    with pytest.raises(BrowserToolError):
        await ask_about_screenshot("prompt", mode="selector", selector="   ")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_selector_missing_element(monkeypatch: pytest.MonkeyPatch) -> None:
    """Single selector missing should raise a clear error message."""
    page = FakePage(b"page")
    browser = FakeBrowser(page)

    async def fake_get_browser() -> FakeBrowser:
        return browser

    module = importlib.import_module("tools.browser.ask_about_screenshot")
    monkeypatch.setattr(module, "get_browser", fake_get_browser)

    with pytest.raises(BrowserToolError) as excinfo:
        await ask_about_screenshot("Anything", mode="selector", selector="#missing")

    assert "No element matched selector '#missing'" in str(excinfo.value)
