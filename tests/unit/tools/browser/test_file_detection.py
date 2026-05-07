"""Tests for browser file download detection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tools.browser.core._file_detection import (
    DownloadInfo,
    build_download_info_from_path,
    format_download_message,
    is_file_content_type,
    save_response_as_file,
)


# ---------------------------------------------------------------------------
# is_file_content_type
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIsFileContentType:
    """Tests for content-type classification."""

    def test_pdf(self) -> None:
        assert is_file_content_type("application/pdf") is True

    def test_image_png(self) -> None:
        assert is_file_content_type("image/png") is True

    def test_image_jpeg(self) -> None:
        assert is_file_content_type("image/jpeg") is True

    def test_octet_stream(self) -> None:
        assert is_file_content_type("application/octet-stream") is True

    def test_zip(self) -> None:
        assert is_file_content_type("application/zip") is True

    def test_html(self) -> None:
        assert is_file_content_type("text/html") is False

    def test_xhtml(self) -> None:
        assert is_file_content_type("application/xhtml+xml") is False

    def test_json(self) -> None:
        assert is_file_content_type("application/json") is False

    def test_plain_text(self) -> None:
        assert is_file_content_type("text/plain") is False

    def test_xml(self) -> None:
        assert is_file_content_type("application/xml") is False

    def test_with_charset(self) -> None:
        assert is_file_content_type("application/pdf; charset=utf-8") is True

    def test_html_with_charset(self) -> None:
        assert is_file_content_type("text/html; charset=utf-8") is False

    def test_empty_string(self) -> None:
        assert is_file_content_type("") is False

    def test_uppercase(self) -> None:
        assert is_file_content_type("Application/PDF") is True

    def test_javascript(self) -> None:
        assert is_file_content_type("application/javascript") is False

    def test_text_javascript(self) -> None:
        assert is_file_content_type("text/javascript") is False

    def test_css(self) -> None:
        assert is_file_content_type("text/css") is False

    def test_svg(self) -> None:
        assert is_file_content_type("image/svg+xml") is False

    def test_wasm(self) -> None:
        assert is_file_content_type("application/wasm") is False


# ---------------------------------------------------------------------------
# save_response_as_file
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSaveResponseAsFile:
    """Tests for saving response body to disk."""

    @pytest.mark.asyncio
    async def test_saves_file(self, tmp_path: Path) -> None:
        """Response body is saved to disk with correct metadata."""
        body = b"%PDF-1.4 fake pdf content"
        response = AsyncMock()
        response.body = AsyncMock(return_value=body)
        response.url = "https://example.com/docs/report.pdf"
        response.headers = {"content-type": "application/pdf"}

        info = await save_response_as_file(response, downloads_dir=tmp_path)

        assert info.filename == "report.pdf"
        assert info.content_type == "application/pdf"
        assert info.size_bytes == len(body)
        assert info.path == str(tmp_path / "report.pdf")
        assert Path(info.path).read_bytes() == body

    @pytest.mark.asyncio
    async def test_deduplicates_filename(self, tmp_path: Path) -> None:
        """Duplicate filenames get a UUID suffix."""
        (tmp_path / "report.pdf").write_bytes(b"existing")
        response = AsyncMock()
        response.body = AsyncMock(return_value=b"%PDF-1.4 new content")
        response.url = "https://example.com/report.pdf"
        response.headers = {"content-type": "application/pdf"}

        info = await save_response_as_file(response, downloads_dir=tmp_path)

        assert info.filename != "report.pdf"
        assert info.filename.startswith("report_")
        assert info.filename.endswith(".pdf")

    @pytest.mark.asyncio
    async def test_generates_filename_for_long_basename(self, tmp_path: Path) -> None:
        """URLs with excessively long basenames get a generated name."""
        response = AsyncMock()
        response.body = AsyncMock(return_value=b"image data")
        response.url = f"https://example.com/{'x' * 201}"
        response.headers = {"content-type": "image/png"}

        info = await save_response_as_file(response, downloads_dir=tmp_path)

        assert info.filename.endswith(".png")
        assert len(info.filename) < 50

    @pytest.mark.asyncio
    async def test_refetches_when_viewer_html(self, tmp_path: Path) -> None:
        """Re-fetches raw bytes when Chromium returns PDF viewer HTML."""
        viewer_html = (
            b"<!doctype html><html><body><embed name='X' "
            b"src='about:blank' type='application/pdf'></body></html>"
        )
        real_pdf = b"%PDF-1.4 real pdf content here"

        # Mock the API request context for re-fetch
        api_response = AsyncMock()
        api_response.body = AsyncMock(return_value=real_pdf)
        api_response.dispose = AsyncMock()

        mock_request = AsyncMock()
        mock_request.get = AsyncMock(return_value=api_response)

        mock_context = MagicMock()
        mock_context.request = mock_request

        mock_page = MagicMock()
        mock_page.context = mock_context

        mock_frame = MagicMock()
        mock_frame.page = mock_page

        response = AsyncMock()
        response.body = AsyncMock(return_value=viewer_html)
        response.url = "https://example.com/report.pdf"
        response.headers = {"content-type": "application/pdf"}
        response.frame = mock_frame

        info = await save_response_as_file(response, downloads_dir=tmp_path)

        assert info.size_bytes == len(real_pdf)
        assert Path(info.path).read_bytes() == real_pdf


# ---------------------------------------------------------------------------
# _is_viewer_html
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIsViewerHtml:
    """Tests for Chromium viewer HTML detection."""

    def test_detects_pdf_viewer_wrapper(self) -> None:
        from tools.browser.core._file_detection import _is_viewer_html

        body = (
            b"<!doctype html><html><body><embed name='X' "
            b"src='about:blank' type='application/pdf'></body></html>"
        )
        assert _is_viewer_html(body, "application/pdf") is True

    def test_real_pdf_not_detected(self) -> None:
        from tools.browser.core._file_detection import _is_viewer_html

        assert _is_viewer_html(b"%PDF-1.4 content", "application/pdf") is False

    def test_large_viewer_html_detected_for_pdf(self) -> None:
        """Large HTML bodies are still detected when magic bytes mismatch."""
        from tools.browser.core._file_detection import _is_viewer_html

        # Any body that doesn't start with %PDF is detected as viewer HTML
        big_html = b"<html>" + b"x" * 5000 + b"<embed src='x'>"
        assert _is_viewer_html(big_html, "application/pdf") is True

    def test_real_large_pdf_not_detected(self) -> None:
        from tools.browser.core._file_detection import _is_viewer_html

        assert _is_viewer_html(b"%PDF-1.4" + b"\x00" * 5000, "application/pdf") is False

    def test_html_content_type_not_detected(self) -> None:
        from tools.browser.core._file_detection import _is_viewer_html

        body = b"<html><body><embed src='x'></body></html>"
        assert _is_viewer_html(body, "text/html") is False

    def test_unknown_type_uses_html_marker_fallback(self) -> None:
        """Types without magic bytes fall back to HTML marker detection."""
        from tools.browser.core._file_detection import _is_viewer_html

        body = b"<html><body><embed src='x'></body></html>"
        assert _is_viewer_html(body, "image/tiff") is True
        assert _is_viewer_html(b"\x49\x49\x2a\x00", "image/tiff") is False

    def test_empty_body(self) -> None:
        from tools.browser.core._file_detection import _is_viewer_html

        assert _is_viewer_html(b"", "application/pdf") is False


# ---------------------------------------------------------------------------
# build_download_info_from_path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildDownloadInfoFromPath:
    """Tests for building DownloadInfo from an existing file."""

    def test_builds_info(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("a,b,c\n1,2,3")
        info = build_download_info_from_path(f)

        assert info.filename == "data.csv"
        assert info.content_type == "text/csv"
        assert info.size_bytes > 0
        assert info.path == str(f)

    def test_unknown_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "mystery.xyz123"
        f.write_bytes(b"\x00\x01")
        info = build_download_info_from_path(f)

        assert info.content_type == "application/octet-stream"


# ---------------------------------------------------------------------------
# format_download_message
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatDownloadMessage:
    """Tests for the human-readable download message."""

    def test_message_contains_path(self) -> None:
        info = DownloadInfo(
            path="/home/computron/file.pdf",
            content_type="application/pdf",
            size_bytes=12345,
            filename="file.pdf",
        )
        msg = format_download_message(info)
        assert "/home/computron/file.pdf" in msg
        assert "application/pdf" in msg
        assert "12.1 KB" in msg


# ---------------------------------------------------------------------------
# open_url file detection integration
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOpenUrlFileDetection:
    """Tests for open_url detecting file downloads."""

    @pytest.mark.asyncio
    async def test_open_url_detects_pdf(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """open_url returns download message string for PDF."""
        from tools.browser.core.browser import BrowserInteractionResult

        pdf_body = b"%PDF-1.4 test"
        download_info = DownloadInfo(
            path="/home/computron/test.pdf",
            content_type="application/pdf",
            size_bytes=len(pdf_body),
            filename="test.pdf",
        )

        result = BrowserInteractionResult(
            navigation_response=None,
            download=download_info,
        )

        mock_browser = AsyncMock()
        mock_browser.navigate = AsyncMock(return_value=result)

        async def _get_browser():
            return mock_browser

        monkeypatch.setattr("tools.browser.events.get_browser", _get_browser)
        monkeypatch.setattr("tools.browser.page.browser_core.get_browser", _get_browser)

        from tools.browser.page import open_url

        output = await open_url("https://example.com/test.pdf")

        assert isinstance(output, str)
        assert "test.pdf" in output
        assert "/home/computron/test.pdf" in output
        assert "application/pdf" in output

    @pytest.mark.asyncio
    async def test_open_url_normal_html(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """open_url returns formatted string for HTML responses."""
        from tools.browser.core.browser import ActiveView, BrowserInteractionResult
        from tools.browser.core.page_view import PageView

        result = BrowserInteractionResult(
            navigation_response=None,
            download=None,
        )

        mock_view = ActiveView(frame=AsyncMock(), title="Test", url="https://example.com")

        mock_browser = AsyncMock()
        mock_browser.navigate = AsyncMock(return_value=result)
        mock_browser.active_view = AsyncMock(return_value=mock_view)

        async def _get_browser() -> object:
            return mock_browser

        monkeypatch.setattr("tools.browser.events.get_browser", _get_browser)
        monkeypatch.setattr("tools.browser.page.browser_core.get_browser", _get_browser)
        # _format_result calls get_browser from interactions module
        monkeypatch.setattr("tools.browser.interactions.get_browser", _get_browser)

        async def _mock_build(view: object, response: object) -> PageView:
            return PageView(
                title="Test",
                url="https://example.com",
                status_code=200,
                content="[heading] Welcome",
                viewport={"scroll_top": 0, "viewport_height": 768, "viewport_width": 1280, "document_height": 1000},
                truncated=False,
            )

        monkeypatch.setattr("tools.browser.interactions.build_page_view", _mock_build)

        from tools.browser.page import open_url

        output = await open_url("https://example.com")

        assert isinstance(output, str)
        assert "Test" in output
        assert "Welcome" in output


# ---------------------------------------------------------------------------
# _format_result file detection
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatResultFileDetection:
    """Tests for _format_result detecting downloads."""

    @pytest.mark.asyncio
    async def test_format_result_returns_download(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_format_result returns download message string when detected."""
        from tools.browser.core.browser import BrowserInteractionResult
        from tools.browser.interactions import _format_result

        download_info = DownloadInfo(
            path="/home/computron/doc.pdf",
            content_type="application/pdf",
            size_bytes=5000,
            filename="doc.pdf",
        )

        result = BrowserInteractionResult(
            navigation_response=None,
            download=download_info,
        )

        output = await _format_result(result)

        assert isinstance(output, str)
        assert "doc.pdf" in output
        assert "/home/computron/doc.pdf" in output

    @pytest.mark.asyncio
    async def test_format_result_normal_page(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_format_result returns formatted string when no download."""
        from tools.browser.core.browser import BrowserInteractionResult
        from tools.browser.core.page_view import PageView
        from tools.browser.interactions import _format_result

        result = BrowserInteractionResult(
            navigation_response=None,
            download=None,
        )

        async def _mock_build(response: object) -> PageView:
            return PageView(
                title="Test",
                url="https://example.com",
                status_code=200,
                content="content here",
                viewport={"scroll_top": 0, "viewport_height": 768, "viewport_width": 1280, "document_height": 1000},
                truncated=False,
            )

        monkeypatch.setattr("tools.browser.interactions._build_snapshot", _mock_build)

        output = await _format_result(result)

        assert isinstance(output, str)
        assert "Test" in output
        assert "content here" in output
