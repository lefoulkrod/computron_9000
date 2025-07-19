import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from config import (
    AppConfig,
    ModelConfig,
    SearchGoogleConfig,
    Settings,
    ToolsConfig,
    WebToolsConfig,
)
from tools.web.search_google import (
    GoogleSearchError,
    GoogleSearchResults,
    search_google,
)

PLAYWRIGHT_BROWSERS = Path(
    os.environ.get("PLAYWRIGHT_BROWSERS_PATH", Path.home() / ".cache/ms-playwright")
)
PLAYWRIGHT_INSTALLED = (
    shutil.which("playwright") is not None and PLAYWRIGHT_BROWSERS.exists()
)


# ---------------------------------------------------------------------------
# Helper stubs for unit tests
# ---------------------------------------------------------------------------
class _DummyKeyboard:
    async def type(self, *args, **kwargs):
        return None

    async def press(self, *args, **kwargs):
        return None


class _DummyElement:
    async def click(self):
        return None


class _DummyPage:
    def __init__(self) -> None:
        self.url = "https://www.google.com"
        self.keyboard = _DummyKeyboard()

    async def route(self, *args, **kwargs):
        return None

    async def goto(self, url, **kwargs):
        self.url = url
        return type("Response", (), {"url": url})()

    async def wait_for_selector(self, *_, **__):
        return _DummyElement()

    async def wait_for_load_state(self, *_, **__):
        return None

    async def wait_for_url(self, *_, **__):
        return None

    async def evaluate(self, *_):
        return [
            {
                "title": "Result 1",
                "link": "http://example.com/1",
                "snippet": "Snippet 1",
            },
            {
                "title": "Result 2",
                "link": "http://example.com/2",
                "snippet": "Snippet 2",
            },
        ]

    async def close(self):
        return None


class _DummyContext:
    async def new_page(self):
        return _DummyPage()

    async def storage_state(self, *_, **__):
        return None

    async def close(self):
        return None


class _DummyBrowser:
    async def new_context(self, *_, **__):
        return _DummyContext()

    async def close(self):
        return None


class _DummyChromium:
    async def launch(self, *_, **__):
        return _DummyBrowser()


class _DummyPlaywright:
    def __init__(self) -> None:
        self.chromium = _DummyChromium()


class _DummyAsyncPlaywright:
    async def __aenter__(self):
        return _DummyPlaywright()

    async def __aexit__(self, exc_type, exc, tb):
        return None


def _dummy_async_playwright():
    return _DummyAsyncPlaywright()


class _FailingAsyncPlaywright:
    async def __aenter__(self):
        raise RuntimeError("fail")

    async def __aexit__(self, exc_type, exc, tb):
        return None


def _failing_async_playwright():
    return _FailingAsyncPlaywright()


# ---------------------------------------------------------------------------
# Utility to build a minimal config object
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        models=[ModelConfig(name="dummy", model="dummy", options={})],
        settings=Settings(home_dir=str(tmp_path), default_model="dummy"),
        tools=ToolsConfig(
            web=WebToolsConfig(
                search_google=SearchGoogleConfig(
                    state_file="state.json", no_save_state=True, timeout=1000
                )
            )
        ),
    )


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.unit
async def test_search_google_invalid_query():
    with pytest.raises(GoogleSearchError):
        await search_google("")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_search_google_playwright_failure(tmp_path):
    cfg = _make_config(tmp_path)
    with (
        patch("tools.web.search_google.load_config", return_value=cfg),
        patch(
            "tools.web.search_google.async_playwright", new=_failing_async_playwright
        ),
        pytest.raises(GoogleSearchError),
    ):
        await search_google("foo")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_search_google_success(tmp_path):
    cfg = _make_config(tmp_path)
    with (
        patch("tools.web.search_google.load_config", return_value=cfg),
        patch("tools.web.search_google.async_playwright", new=_dummy_async_playwright),
    ):
        results = await search_google("foo", max_results=2)

    assert isinstance(results, GoogleSearchResults)
    assert len(results.results) == 2
    assert results.results[0].title == "Result 1"


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_google_integration(tmp_path):
    if not PLAYWRIGHT_INSTALLED:
        pytest.skip("Playwright not installed", allow_module_level=True)

    pytest.importorskip("playwright.async_api")
    cfg = _make_config(tmp_path)
    # Use real Playwright but custom config to avoid writing to user home
    with patch("tools.web.search_google.load_config", return_value=cfg):
        results = await search_google("open source software", max_results=1)

    assert isinstance(results, GoogleSearchResults)
    assert len(results.results) >= 1
    assert results.results[0].link.startswith("http")
