"""Legacy placeholder to avoid duplicate tests; coverage lives in module-specific suites."""

from __future__ import annotations

import base64
import importlib
from types import SimpleNamespace
from typing import cast

import pytest

from tools.browser import BrowserToolError
from tools.browser.vision import GroundingResult, ask_about_screenshot, ground_elements_by_text


class _ScreenshotFakeLocator:
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


class _ScreenshotFakePage:
    def __init__(
        self,
        screenshot_bytes: bytes,
        *,
        url: str = "https://example.com",
        locator_map: dict[str, _ScreenshotFakeLocator] | None = None,
    ) -> None:
        self._screenshot_bytes = screenshot_bytes
        self._locator_map = locator_map or {}
        self.url = url

    async def screenshot(self, *, full_page: bool = False, type: str = "png") -> bytes:  # noqa: A003
        assert type == "png"
        if full_page:
            return self._screenshot_bytes
        return self._screenshot_bytes

    def locator(self, selector: str) -> _ScreenshotFakeLocator:
        return self._locator_map.get(selector, _ScreenshotFakeLocator(b"", exists=False))

    def get_by_text(self, value: str, exact: bool = True) -> _ScreenshotFakeLocator:  # noqa: ARG002
        return _ScreenshotFakeLocator(b"", exists=False)


class _GroundingFakePage:
    def __init__(self, screenshot_bytes: bytes, url: str = "https://example.com") -> None:
        self._screenshot_bytes = screenshot_bytes
        self.url = url

    async def screenshot(self, *, full_page: bool = True, type: str = "png") -> bytes:  # noqa: A003
        assert type == "png"
        return self._screenshot_bytes


class _FakeBrowser:
    def __init__(self, page: _ScreenshotFakePage | _GroundingFakePage) -> None:
        self._page = page

    async def current_page(self) -> _ScreenshotFakePage | _GroundingFakePage:
        return self._page


class _FakeModel:
    model = "vision-model"
    options = {"temperature": 0.0}
    think = False


class _FakeConfig:
    class _LLM:
        host = "http://fake-host"

    llm = _LLM()


class _ScreenshotClient:
    called: bool = False
    last_kwargs: dict[str, object] = {}
    last_host: str | None = None

    def __init__(self, host: str | None = None) -> None:
        _ScreenshotClient.last_host = host

    async def generate(self, **kwargs: object) -> SimpleNamespace:
        _ScreenshotClient.called = True
        _ScreenshotClient.last_kwargs = kwargs
        return SimpleNamespace(response="Mock answer")


class _GroundingClient:
    last_prompt: str | None = None
    last_model: object | None = None
    last_images: object | None = None
    last_host: str | None = None

    def __init__(self, host: str | None = None) -> None:
        _GroundingClient.last_host = host

    async def generate(self, **kwargs: object) -> SimpleNamespace:
        _GroundingClient.last_prompt = cast(str | None, kwargs.get("prompt"))
        _GroundingClient.last_model = kwargs.get("model")
        _GroundingClient.last_images = kwargs.get("images")
        payload = '[{"element": "button", "text": "Login", "bbox": [10, 20, 30, 40]}]'
        return SimpleNamespace(response=payload)


class _GroundingDummyClient:
    def __init__(self, host: str | None = None) -> None:  # noqa: D401, ANN204
        self._host = host

    async def generate(self, **kwargs: object) -> SimpleNamespace:  # noqa: ARG002
        return SimpleNamespace(response="not-json")


async def _fake_snapshot(*args: object, **kwargs: object) -> None:  # noqa: ARG001, D401
    return None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ask_about_screenshot_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """ask_about_screenshot should capture a screenshot and forward it to the model."""

    page = _ScreenshotFakePage(b"fake-image-bytes")
    browser = _FakeBrowser(page)

    async def fake_get_browser() -> _FakeBrowser:
        return browser

    fake_model = _FakeModel()

    _ScreenshotClient.called = False
    _ScreenshotClient.last_kwargs = {}
    _ScreenshotClient.last_host = None

    module = importlib.import_module("tools.browser.vision")

    monkeypatch.setattr(module, "get_browser", fake_get_browser)
    monkeypatch.setattr(module, "AsyncClient", _ScreenshotClient)
    monkeypatch.setattr(module, "get_model_by_name", lambda name: fake_model)
    monkeypatch.setattr(module, "load_config", lambda: _FakeConfig())

    answer = await ask_about_screenshot("What is in the header?")

    assert answer == "Mock answer"
    assert _ScreenshotClient.last_host == _FakeConfig.llm.host
    assert _ScreenshotClient.called

    kwargs = _ScreenshotClient.last_kwargs
    assert kwargs["prompt"] == "What is in the header?"
    assert kwargs["model"] == fake_model.model
    images = kwargs["images"]
    assert isinstance(images, list)
    assert len(images) == 1
    encoded = base64.b64encode(b"fake-image-bytes").decode("ascii")
    assert getattr(images[0], "value", None) == encoded


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ask_about_screenshot_rejects_blank_prompt() -> None:
    """Blank prompts should raise a BrowserToolError."""

    with pytest.raises(BrowserToolError):
        await ask_about_screenshot("   ")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ask_about_screenshot_requires_navigation(monkeypatch: pytest.MonkeyPatch) -> None:
    """ask_about_screenshot should require a navigated page."""

    page = _ScreenshotFakePage(b"img", url="about:blank")
    browser = _FakeBrowser(page)

    async def fake_get_browser() -> _FakeBrowser:
        return browser

    module = importlib.import_module("tools.browser.vision")

    monkeypatch.setattr(module, "get_browser", fake_get_browser)

    with pytest.raises(BrowserToolError):
        await ask_about_screenshot("Describe the page")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ask_about_screenshot_selector_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Selector screenshots should focus on the requested element."""

    locator = _ScreenshotFakeLocator(b"element-bytes")
    page = _ScreenshotFakePage(b"page-bytes", locator_map={"#hero": locator})
    browser = _FakeBrowser(page)

    async def fake_get_browser() -> _FakeBrowser:
        return browser

    fake_model = _FakeModel()

    _ScreenshotClient.called = False
    _ScreenshotClient.last_kwargs = {}
    _ScreenshotClient.last_host = None

    module = importlib.import_module("tools.browser.vision")

    monkeypatch.setattr(module, "get_browser", fake_get_browser)
    monkeypatch.setattr(module, "AsyncClient", _ScreenshotClient)
    monkeypatch.setattr(module, "get_model_by_name", lambda name: fake_model)
    monkeypatch.setattr(module, "load_config", lambda: _FakeConfig())

    answer = await ask_about_screenshot("Describe the hero", mode="selector", selector="#hero")

    assert answer == "Mock answer"
    assert _ScreenshotClient.called

    kwargs = _ScreenshotClient.last_kwargs

    images = kwargs.get("images")
    assert isinstance(images, list)
    assert images
    assert getattr(images[0], "value", None) == base64.b64encode(
        b"element-bytes"
    ).decode("ascii")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_selector_requires_non_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Selector mode should reject empty selector handles."""

    page = _ScreenshotFakePage(b"page")
    browser = _FakeBrowser(page)

    async def fake_get_browser() -> _FakeBrowser:
        return browser

    module = importlib.import_module("tools.browser.vision")
    monkeypatch.setattr(module, "get_browser", fake_get_browser)

    with pytest.raises(BrowserToolError):
        await ask_about_screenshot("prompt", mode="selector", selector="   ")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_selector_missing_element(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing selector handles should raise a clear error message."""

    page = _ScreenshotFakePage(b"page")
    browser = _FakeBrowser(page)

    async def fake_get_browser() -> _FakeBrowser:
        return browser

    module = importlib.import_module("tools.browser.vision")
    monkeypatch.setattr(module, "get_browser", fake_get_browser)

    with pytest.raises(BrowserToolError) as excinfo:
        await ask_about_screenshot("Anything", mode="selector", selector="#missing")

    msg = str(excinfo.value)
    assert "No element matched selector handle '#missing'" in msg or "No element matched selector '#missing'" in msg


@pytest.mark.unit
@pytest.mark.asyncio
async def test_request_grounding_by_text_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """ground_elements_by_text should return validated GroundingResult objects."""

    page = _GroundingFakePage(b"fake-bytes")
    browser = _FakeBrowser(page)

    module = importlib.import_module("tools.browser.vision")

    async def fake_get_browser() -> _FakeBrowser:
        return browser

    monkeypatch.setattr(module, "get_browser", fake_get_browser)
    monkeypatch.setattr(module, "_build_page_snapshot", _fake_snapshot)
    monkeypatch.setattr(module, "AsyncClient", _GroundingClient)
    monkeypatch.setattr(module, "get_model_by_name", lambda name: _FakeModel())
    monkeypatch.setattr(module, "load_config", lambda: _FakeConfig())

    result = await ground_elements_by_text("Login")

    assert isinstance(result, list)
    assert len(result) == 1
    first = result[0]
    assert isinstance(first, GroundingResult)
    assert first.text == "Login"
    assert first.bbox == (10, 20, 30, 40)
    # selector resolution is best-effort; ensure the field exists (may be None)
    assert hasattr(first, "selector")

    expected_prompt = (
        "You are a UI grounding assistant.\n"
        "Given this screenshot, return bounding boxes for all elements that match the description \"Login\".\n"
        "Format the output strictly as JSON: [{\"element\": \"...\", \"text\": \"...\", \"bbox\": [x,y,width,height]}]"
    )
    assert _GroundingClient.last_prompt == expected_prompt
    assert _GroundingClient.last_model == _FakeModel().model
    assert _GroundingClient.last_host == _FakeConfig.llm.host

    images = _GroundingClient.last_images
    if not isinstance(images, list):
        pytest.fail("Vision client did not receive images list")
    assert len(images) == 1
    expected_image = base64.b64encode(b"fake-bytes").decode("ascii")
    assert getattr(images[0], "value", None) == expected_image


@pytest.mark.unit
@pytest.mark.asyncio
async def test_request_grounding_by_text_requires_navigation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Grounding requests should fail when the page is not navigated."""

    page = _GroundingFakePage(b"bytes", url="about:blank")
    browser = _FakeBrowser(page)
    module = importlib.import_module("tools.browser.vision")

    async def fake_get_browser() -> _FakeBrowser:
        return browser

    monkeypatch.setattr(module, "get_browser", fake_get_browser)

    with pytest.raises(BrowserToolError):
        await ground_elements_by_text("Login")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_request_grounding_by_text_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid JSON responses should raise a BrowserToolError."""

    page = _GroundingFakePage(b"fake", url="https://example.com")
    browser = _FakeBrowser(page)
    module = importlib.import_module("tools.browser.vision")

    async def fake_get_browser() -> _FakeBrowser:
        return browser

    monkeypatch.setattr(module, "get_browser", fake_get_browser)
    monkeypatch.setattr(module, "_build_page_snapshot", _fake_snapshot)
    monkeypatch.setattr(module, "AsyncClient", _GroundingDummyClient)
    monkeypatch.setattr(module, "get_model_by_name", lambda name: _FakeModel())
    monkeypatch.setattr(module, "load_config", lambda: _FakeConfig())

    with pytest.raises(BrowserToolError):
        await ground_elements_by_text("Login")
