"""Tests for tools.web.fetch_url."""

from __future__ import annotations

import sys
from pathlib import Path

import aiohttp
import pytest

from tools.web.fetch_url import fetch_url

# The package re-exports the `fetch_url` function under the name
# `tools.web.fetch_url`, shadowing the submodule — grab the real module
# object from sys.modules so monkeypatch can reach module-level globals.
fetch_mod = sys.modules["tools.web.fetch_url"]

_URL = "https://example.test/page"


class _FakeResponse:
    """Stand-in for an aiohttp response used as an async context manager."""

    def __init__(self, *, status: int, content_type: str, body: str | bytes) -> None:
        self.status = status
        self.headers = {"Content-Type": content_type}
        self._body = body

    async def text(self) -> str:
        assert isinstance(self._body, str)
        return self._body

    async def read(self) -> bytes:
        return self._body if isinstance(self._body, bytes) else self._body.encode()

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False


class _FakeSession:
    """Stand-in for aiohttp.ClientSession."""

    def __init__(self, response: _FakeResponse | None, exc: Exception | None) -> None:
        self._response = response
        self._exc = exc

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    def get(self, url: str, allow_redirects: bool = True) -> _FakeResponse:
        if self._exc is not None:
            raise self._exc
        assert self._response is not None
        return self._response


def _patch_http(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    status: int = 200,
    content_type: str = "text/html",
    body: str | bytes = "<html><body><p>hello</p></body></html>",
    exc: Exception | None = None,
) -> None:
    """Patch aiohttp + the save dir so fetch_url runs offline against *tmp_path*."""
    response = None if exc else _FakeResponse(
        status=status, content_type=content_type, body=body
    )
    session = _FakeSession(response, exc)
    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **k: session)
    monkeypatch.setattr(fetch_mod, "_SAVE_DIR", tmp_path)


def _patch_extract(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    """Force trafilatura extraction to return a fixed value."""
    monkeypatch.setattr(fetch_mod, "_extract_markdown", lambda _html: value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_url_returns_text_and_saves_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A normal page returns a header + inline text and writes the full file."""
    _patch_http(monkeypatch, tmp_path)
    _patch_extract(monkeypatch, "# Heading\n\nBody paragraph.")

    out = await fetch_url(_URL)

    assert "HTTP 200" in out
    assert "Heading" in out
    assert "Body paragraph." in out
    assert "truncated" not in out
    saved = list(tmp_path.glob("fetch_*.md"))
    assert len(saved) == 1
    assert "Heading" in saved[0].read_text()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_url_truncates_long_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A long page is truncated inline but saved in full to the file."""
    full = "x" * (fetch_mod._INLINE_BUDGET + 5000)
    _patch_http(monkeypatch, tmp_path)
    _patch_extract(monkeypatch, full)

    out = await fetch_url(_URL)

    assert "truncated" in out
    saved = list(tmp_path.glob("fetch_*.md"))[0]
    # The full document is on disk; only a budget-sized slice is inline.
    assert len(saved.read_text()) == len(full)
    assert len(out) < len(full)
    assert str(saved) in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_url_non_web_content_saved_and_path_returned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Non-web content (e.g. a PDF) is saved to a file and its path returned."""
    _patch_http(
        monkeypatch, tmp_path,
        content_type="application/pdf", body=b"%PDF-1.4 binary bytes",
    )

    out = await fetch_url(_URL)

    saved = list(tmp_path.glob("fetch_*.pdf"))
    assert len(saved) == 1
    assert saved[0].read_bytes() == b"%PDF-1.4 binary bytes"
    assert str(saved[0]) in out
    assert "application/pdf" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_url_http_error_returns_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A 4xx/5xx status returns a plain blocked message, not raise."""
    _patch_http(monkeypatch, tmp_path, status=403, body="forbidden")

    out = await fetch_url(_URL)

    assert "HTTP 403" in out
    assert "full browser" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_url_bot_wall_returns_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An anti-bot challenge page returns a fallback message."""
    _patch_http(
        monkeypatch, tmp_path,
        body="<html><title>Just a moment...</title><body>checking</body></html>",
    )

    out = await fetch_url(_URL)

    assert "anti-bot" in out.lower()
    assert "full browser" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_url_network_error_returns_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A network failure returns a plain message instead of raising."""
    _patch_http(
        monkeypatch, tmp_path,
        exc=aiohttp.ClientConnectionError("connection refused"),
    )

    out = await fetch_url(_URL)

    assert "Could not fetch" in out
    assert "full browser" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_url_no_extractable_content_returns_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When trafilatura finds no content, a plain message is returned."""
    _patch_http(monkeypatch, tmp_path)
    _patch_extract(monkeypatch, None)

    out = await fetch_url(_URL)

    assert "No readable content" in out
    assert "full browser" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_url_plain_text_passthrough(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """text/plain content is returned as-is without extraction."""
    _patch_http(
        monkeypatch, tmp_path,
        content_type="text/plain", body="raw plain text body",
    )
    # Extraction must not be consulted for text/plain.
    _patch_extract(monkeypatch, None)

    out = await fetch_url(_URL)

    assert "raw plain text body" in out


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_url_markdown_passthrough(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """text/markdown content is returned as-is, not run through extraction."""
    _patch_http(
        monkeypatch, tmp_path,
        content_type="text/markdown",
        body="# Title\n\nAlready markdown, [link](https://x.test).",
    )
    # Extraction must not touch already-markdown content.
    _patch_extract(monkeypatch, None)

    out = await fetch_url(_URL)

    assert "# Title" in out
    assert "[link](https://x.test)" in out


_ARTICLE_HTML = """<html><head><title>Guide</title></head><body>
<nav>Home About Contact</nav>
<article>
<h1>Installing the Widget</h1>
<p>The widget is a small component you add to any page. It is designed to be
lightweight and easy to integrate into existing projects without much fuss.</p>
<h2>Prerequisites</h2>
<p>Before you begin, make sure you have Node eighteen or higher installed.
See the official <a href="https://nodejs.org/download">Node download page</a>.</p>
<ul><li>Node 18 or newer</li><li>A package manager</li></ul>
</article>
<footer>Copyright 2026</footer>
</body></html>"""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_url_real_extraction_produces_markdown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End-to-end with real trafilatura: markdown structure and links survive,
    page chrome is stripped."""
    _patch_http(monkeypatch, tmp_path, body=_ARTICLE_HTML)

    out = await fetch_url(_URL)

    assert "# Installing the Widget" in out
    assert "## Prerequisites" in out
    assert "[Node download page](https://nodejs.org/download)" in out
    # nav / footer chrome is dropped by the extractor
    assert "Home About Contact" not in out
    assert "Copyright 2026" not in out
