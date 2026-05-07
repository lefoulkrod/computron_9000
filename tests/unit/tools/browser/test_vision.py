"""Tests for browser vision tools (inspect_page + browser_visual_action)."""

from __future__ import annotations

import base64
import importlib

import pytest

from tools._grounding import GroundingResponse
from tools.browser import BrowserToolError
from tools.browser.vision import inspect_page, browser_visual_action


# ── Shared helpers ────────────────────────────────────────────────────


def _make_fake_get_active_view(browser):
    """Build a fake ``get_active_view`` from a ``_FakeBrowser``."""

    async def _fake(tool_name):
        view = await browser.active_view()
        if view.url in {"", "about:blank"}:
            raise BrowserToolError("Navigate to a page first.", tool=tool_name)
        return browser, view

    return _fake


class _ScreenshotFakeLocator:
    def __init__(self, screenshot_bytes: bytes, exists: bool = True) -> None:
        self._screenshot_bytes = screenshot_bytes
        self._exists = exists
        self.first = self

    async def count(self) -> int:
        return 1 if self._exists else 0

    async def screenshot(self, *, type: str = "png") -> bytes:
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
        self.viewport_size = {"width": 1024, "height": 768}

    async def screenshot(self, *, full_page: bool = False, type: str = "png") -> bytes:
        assert type == "png"
        return self._screenshot_bytes

    async def evaluate(self, script: str, arg: object = None) -> str | dict:
        return ""

    def locator(self, selector: str) -> _ScreenshotFakeLocator:
        return self._locator_map.get(selector, _ScreenshotFakeLocator(b"", exists=False))

    def get_by_text(self, value: str, exact: bool = True) -> _ScreenshotFakeLocator:
        return _ScreenshotFakeLocator(b"", exists=False)

    def get_by_alt_text(self, value: str, exact: bool = True) -> _ScreenshotFakeLocator:
        return _ScreenshotFakeLocator(b"", exists=False)


class _FakeBrowser:
    def __init__(self, page: _ScreenshotFakePage) -> None:
        self._page = page

    async def current_page(self) -> _ScreenshotFakePage:
        return self._page

    async def active_frame(self) -> _ScreenshotFakePage:
        return self._page

    async def active_view(self):
        from tools.browser.core.browser import ActiveView

        return ActiveView(frame=self._page, title="Example", url=self._page.url)

    async def perform_interaction(self, action_fn):
        from tools.browser.core.browser import BrowserInteractionResult

        await action_fn()
        return BrowserInteractionResult(
            action_ms=10.0,
            settle_timings=None,
            navigation_response=None,
        )


_FAKE_SETTINGS = {
    "vision_model": "vision-model",
    "vision_options": {"temperature": 0.0},
    "vision_think": False,
}


async def _fake_vision_generate(prompt, image_base64, *, media_type="image/png"):
    """Stand-in for sdk.providers.vision_generate."""
    _fake_vision_generate.called = True
    _fake_vision_generate.last_prompt = prompt
    _fake_vision_generate.last_image = image_base64
    return "Mock answer"


_fake_vision_generate.called = False
_fake_vision_generate.last_prompt = None
_fake_vision_generate.last_image = None


# ── inspect_page tests ────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_inspect_page_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """inspect_page should capture a screenshot and forward it to the provider."""
    from unittest.mock import patch

    page = _ScreenshotFakePage(b"fake-image-bytes")
    browser = _FakeBrowser(page)

    _fake_vision_generate.called = False
    _fake_vision_generate.last_prompt = None
    _fake_vision_generate.last_image = None

    module = importlib.import_module("tools.browser.vision")
    import settings as settings_module

    monkeypatch.setattr(module, "get_active_view", _make_fake_get_active_view(browser))
    monkeypatch.setattr(settings_module, "load_settings", lambda: dict(_FAKE_SETTINGS))

    with patch("sdk.providers.vision_generate", _fake_vision_generate):
        answer = await inspect_page("What is in the header?")

    assert answer == "Mock answer"
    assert _fake_vision_generate.called
    assert _fake_vision_generate.last_prompt == "What is in the header?"
    encoded = base64.b64encode(b"fake-image-bytes").decode("ascii")
    assert _fake_vision_generate.last_image == encoded


@pytest.mark.unit
@pytest.mark.asyncio
async def test_inspect_page_rejects_blank_prompt() -> None:
    """Blank prompts should raise a BrowserToolError."""
    with pytest.raises(BrowserToolError):
        await inspect_page("   ")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_inspect_page_requires_navigation(monkeypatch: pytest.MonkeyPatch) -> None:
    """inspect_page should require a navigated page."""
    page = _ScreenshotFakePage(b"img", url="about:blank")
    browser = _FakeBrowser(page)

    async def fake_get_browser() -> _FakeBrowser:
        return browser

    module = importlib.import_module("tools.browser.vision")

    monkeypatch.setattr(module, "get_browser", fake_get_browser)
    monkeypatch.setattr(module, "get_active_view", _make_fake_get_active_view(browser))

    with pytest.raises(BrowserToolError):
        await inspect_page("Describe the page")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_inspect_page_selector_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Selector screenshots should focus on the requested element."""
    from unittest.mock import patch

    locator = _ScreenshotFakeLocator(b"element-bytes")
    page = _ScreenshotFakePage(b"page-bytes", locator_map={"#hero": locator})
    browser = _FakeBrowser(page)

    _fake_vision_generate.called = False
    _fake_vision_generate.last_image = None

    module = importlib.import_module("tools.browser.vision")
    import settings as settings_module

    async def _get_browser():
        return browser

    monkeypatch.setattr(module, "get_browser", _get_browser)
    monkeypatch.setattr(module, "get_active_view", _make_fake_get_active_view(browser))
    monkeypatch.setattr(settings_module, "load_settings", lambda: dict(_FAKE_SETTINGS))

    with patch("sdk.providers.vision_generate", _fake_vision_generate):
        answer = await inspect_page("Describe the hero", mode="selector", selector="#hero")

    assert answer == "Mock answer"
    assert _fake_vision_generate.called
    assert _fake_vision_generate.last_image == base64.b64encode(
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
    monkeypatch.setattr(module, "get_active_view", _make_fake_get_active_view(browser))

    with pytest.raises(BrowserToolError):
        await inspect_page("prompt", mode="selector", selector="   ")


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
    monkeypatch.setattr(module, "get_active_view", _make_fake_get_active_view(browser))

    with pytest.raises(BrowserToolError) as excinfo:
        await inspect_page("Anything", mode="selector", selector="#missing")

    msg = str(excinfo.value)
    assert "No element matched selector handle '#missing'" in msg or "No element matched selector '#missing'" in msg


# ── browser_visual_action tests ───────────────────────────────────────


_CLICK_GROUNDING_RESPONSE = GroundingResponse(
    x=500,
    y=300,
    thought="Found the login button",
    action_type="click",
    raw={"x": 500, "y": 300, "coordinates": [{"screen": [500, 300]}]},
)

_TYPE_GROUNDING_RESPONSE = GroundingResponse(
    x=None,
    y=None,
    thought="Need to type text",
    action_type="type",
    raw={"type_content": "hello world"},
)

_FINISHED_GROUNDING_RESPONSE = GroundingResponse(
    x=None,
    y=None,
    thought="Done",
    action_type="finished",
    raw={"finished_content": "Login was successful"},
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_browser_visual_action_click(monkeypatch: pytest.MonkeyPatch) -> None:
    """browser_visual_action with a click response should execute the click."""
    page = _ScreenshotFakePage(b"fake-bytes")
    browser = _FakeBrowser(page)

    module = importlib.import_module("tools.browser.vision")
    grounding_module = importlib.import_module("tools._grounding")

    monkeypatch.setattr(module, "get_active_view", _make_fake_get_active_view(browser))

    async def fake_run_grounding(screenshot_bytes, task, *, screenshot_filename=""):
        return _CLICK_GROUNDING_RESPONSE

    monkeypatch.setattr(grounding_module, "run_grounding", fake_run_grounding)

    # Mock execute_action to avoid needing real Playwright
    from unittest.mock import AsyncMock

    mock_execute = AsyncMock()
    monkeypatch.setattr("tools.browser._action_map.execute_action", mock_execute)

    # Mock _format_result — it's imported lazily inside browser_visual_action
    interactions_module = importlib.import_module("tools.browser.interactions")

    async def fake_format_result(result, *, tool_name="", resolution=None):
        return "[page snapshot]"

    monkeypatch.setattr(interactions_module, "_format_result", fake_format_result)

    result = await browser_visual_action("Click the login button")
    assert isinstance(result, str)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_browser_visual_action_finished(monkeypatch: pytest.MonkeyPatch) -> None:
    """browser_visual_action with finished response should return snapshot with note."""
    page = _ScreenshotFakePage(b"fake-bytes")
    browser = _FakeBrowser(page)

    module = importlib.import_module("tools.browser.vision")
    grounding_module = importlib.import_module("tools._grounding")

    monkeypatch.setattr(module, "get_active_view", _make_fake_get_active_view(browser))

    async def fake_run_grounding(screenshot_bytes, task, *, screenshot_filename=""):
        return _FINISHED_GROUNDING_RESPONSE

    monkeypatch.setattr(grounding_module, "run_grounding", fake_run_grounding)

    # Mock build_page_view — it's lazy-imported inside browser_visual_action
    from tools.browser.core.page_view import PageView
    page_view_module = importlib.import_module("tools.browser.core.page_view")

    fake_snapshot = PageView(
        title="Test Page",
        url="https://example.com",
        status_code=200,
        content="Page content here",
        viewport=None,
        truncated=False,
        snapshot_nodes=0,
        snapshot_js_ms=0.0,
        snapshot_py_ms=0.0,
    )

    async def fake_build_page_view(view, response):
        return fake_snapshot

    monkeypatch.setattr(page_view_module, "build_page_view", fake_build_page_view)

    result = await browser_visual_action("Check if login succeeded")
    assert "finished" in result.lower() or "Login was successful" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_browser_visual_action_empty_task() -> None:
    """Empty task should raise BrowserToolError."""
    with pytest.raises(BrowserToolError):
        await browser_visual_action("   ")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_browser_visual_action_grounding_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """RuntimeError from grounding should become BrowserToolError."""
    page = _ScreenshotFakePage(b"fake")
    browser = _FakeBrowser(page)

    module = importlib.import_module("tools.browser.vision")
    grounding_module = importlib.import_module("tools._grounding")

    monkeypatch.setattr(module, "get_active_view", _make_fake_get_active_view(browser))

    async def failing_grounding(*args, **kwargs):
        raise RuntimeError("Grounding failed: container not running")

    monkeypatch.setattr(grounding_module, "run_grounding", failing_grounding)

    with pytest.raises(BrowserToolError, match="Grounding request failed"):
        await browser_visual_action("Click login")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_browser_visual_action_requires_navigation(monkeypatch: pytest.MonkeyPatch) -> None:
    """browser_visual_action should require a navigated page."""
    page = _ScreenshotFakePage(b"bytes", url="about:blank")
    browser = _FakeBrowser(page)
    module = importlib.import_module("tools.browser.vision")

    monkeypatch.setattr(module, "get_active_view", _make_fake_get_active_view(browser))

    with pytest.raises(BrowserToolError):
        await browser_visual_action("Click login")
