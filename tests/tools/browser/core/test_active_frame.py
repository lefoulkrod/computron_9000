"""Tests for dominant iframe detection and active_frame() behaviour."""

from __future__ import annotations

from typing import Any

import pytest

from tools.browser.core.browser import Browser


class _FakeFrameElement:
    """Stub for the element returned by frame.frame_element()."""

    def __init__(self, box: dict[str, float] | None) -> None:
        self._box = box

    async def bounding_box(self) -> dict[str, float] | None:
        return self._box


class _FakeFrame:
    """Minimal Frame stub for _detect_dominant_frame tests."""

    def __init__(
        self,
        *,
        url: str = "https://iframe.test/widget",
        detached: bool = False,
        box: dict[str, float] | None = None,
        child_count: int = 5,
        cross_origin: bool = False,
    ) -> None:
        self.url = url
        self._detached = detached
        self._box = box
        self._child_count = child_count
        self._cross_origin = cross_origin
        self._element = _FakeFrameElement(box)

    def is_detached(self) -> bool:
        return self._detached

    async def frame_element(self) -> _FakeFrameElement:
        return self._element

    async def evaluate(self, script: str) -> Any:
        if self._cross_origin:
            raise Exception("Execution context was destroyed")
        return self._child_count


class _FakePage:
    """Minimal Page stub exposing frames and viewport_size."""

    def __init__(
        self,
        *,
        frames: list[Any] | None = None,
        viewport: dict[str, int] | None = None,
    ) -> None:
        self.frames = frames or []
        self.viewport_size = viewport or {"width": 1280, "height": 800}
        self.main_frame = object()
        # Prepend main_frame to the frames list so page.frames includes it
        self.frames.insert(0, self.main_frame)
        self.url = "https://example.test"

    def is_closed(self) -> bool:
        return False

    def on(self, event: str, callback: Any) -> None:
        pass


class _FakeContext:
    def __init__(self, pages: list[Any]) -> None:
        self.pages = pages


def _make_browser(page: _FakePage) -> Browser:
    """Create a Browser wrapping a fake context containing one page."""
    ctx = _FakeContext(pages=[page])
    browser = Browser(context=ctx)  # type: ignore[arg-type]
    return browser


# ---- _detect_dominant_frame tests ----


@pytest.mark.unit
@pytest.mark.asyncio
async def test_detect_no_iframes_returns_none() -> None:
    """No iframes on page -> None."""
    page = _FakePage()
    browser = _make_browser(page)
    result = await browser._detect_dominant_frame(page)  # type: ignore[arg-type]
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_detect_large_iframe_returns_frame() -> None:
    """An iframe covering >25% of viewport is detected."""
    frame = _FakeFrame(box={"x": 0, "y": 0, "width": 1000, "height": 700})
    page = _FakePage(frames=[frame])
    browser = _make_browser(page)
    result = await browser._detect_dominant_frame(page)  # type: ignore[arg-type]
    assert result is frame


@pytest.mark.unit
@pytest.mark.asyncio
async def test_detect_small_iframe_returns_none() -> None:
    """An iframe smaller than 25% of viewport is ignored."""
    # Viewport is 1280x800 = 1_024_000.  25% = 256_000.
    # This frame is 200x200 = 40_000 — well below threshold.
    frame = _FakeFrame(box={"x": 10, "y": 10, "width": 200, "height": 200})
    page = _FakePage(frames=[frame])
    browser = _make_browser(page)
    result = await browser._detect_dominant_frame(page)  # type: ignore[arg-type]
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_detect_cross_origin_iframe_skipped() -> None:
    """Cross-origin iframe (evaluate throws) is skipped."""
    frame = _FakeFrame(
        box={"x": 0, "y": 0, "width": 1200, "height": 700},
        cross_origin=True,
    )
    page = _FakePage(frames=[frame])
    browser = _make_browser(page)
    result = await browser._detect_dominant_frame(page)  # type: ignore[arg-type]
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_detect_detached_iframe_skipped() -> None:
    """Detached iframe is skipped."""
    frame = _FakeFrame(
        box={"x": 0, "y": 0, "width": 1200, "height": 700},
        detached=True,
    )
    page = _FakePage(frames=[frame])
    browser = _make_browser(page)
    result = await browser._detect_dominant_frame(page)  # type: ignore[arg-type]
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_detect_empty_iframe_skipped() -> None:
    """Iframe with no children is skipped."""
    frame = _FakeFrame(
        box={"x": 0, "y": 0, "width": 1200, "height": 700},
        child_count=0,
    )
    page = _FakePage(frames=[frame])
    browser = _make_browser(page)
    result = await browser._detect_dominant_frame(page)  # type: ignore[arg-type]
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_detect_picks_largest_frame() -> None:
    """When multiple qualifying frames exist, the largest wins."""
    small = _FakeFrame(
        url="https://small.test",
        box={"x": 0, "y": 0, "width": 700, "height": 500},
    )
    large = _FakeFrame(
        url="https://large.test",
        box={"x": 0, "y": 0, "width": 1200, "height": 750},
    )
    page = _FakePage(frames=[small, large])
    browser = _make_browser(page)
    result = await browser._detect_dominant_frame(page)  # type: ignore[arg-type]
    assert result is large


# ---- active_frame tests ----


@pytest.mark.unit
@pytest.mark.asyncio
async def test_active_frame_returns_page_when_no_frame() -> None:
    """With no active frame, active_frame() returns the page."""
    page = _FakePage()
    browser = _make_browser(page)
    result = await browser.active_frame()
    assert result is page


@pytest.mark.unit
@pytest.mark.asyncio
async def test_active_frame_returns_tracked_frame() -> None:
    """When _active_frame is set, active_frame() returns it."""
    page = _FakePage()
    browser = _make_browser(page)
    frame = _FakeFrame()
    browser._active_frame = frame  # type: ignore[assignment]
    result = await browser.active_frame()
    assert result is frame


@pytest.mark.unit
@pytest.mark.asyncio
async def test_active_frame_falls_back_on_detach() -> None:
    """When the tracked frame detaches, fall back to the page."""
    page = _FakePage()
    browser = _make_browser(page)
    frame = _FakeFrame(detached=True)
    browser._active_frame = frame  # type: ignore[assignment]
    result = await browser.active_frame()
    assert result is page
    # Should have cleared the reference
    assert browser._active_frame is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clear_active_frame() -> None:
    """clear_active_frame() resets _active_frame to None."""
    page = _FakePage()
    browser = _make_browser(page)
    browser._active_frame = _FakeFrame()  # type: ignore[assignment]
    browser.clear_active_frame()
    assert browser._active_frame is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_viewport_returns_none() -> None:
    """When page has no viewport_size, detection returns None."""
    page = _FakePage()
    page.viewport_size = None  # type: ignore[assignment]
    frame = _FakeFrame(box={"x": 0, "y": 0, "width": 1200, "height": 700})
    page.frames.append(frame)
    browser = _make_browser(page)
    result = await browser._detect_dominant_frame(page)  # type: ignore[arg-type]
    assert result is None
