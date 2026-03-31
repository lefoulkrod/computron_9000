"""Tests for tasks._notifier — Telegram push notifications."""

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tasks._notifier import (
    TelegramNotifier,
    format_run_completed,
    format_run_failed,
)


def _make_config(**overrides):
    """Build a minimal NotificationsConfig-like object."""
    from config import NotificationsConfig

    return NotificationsConfig(**overrides)


@pytest.mark.unit
class TestTelegramNotifier:
    """Test TelegramNotifier init and send behavior."""

    def test_enables_when_env_vars_present(self):
        """Notifier is enabled when both env vars are set."""
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "123"}):
            notifier = TelegramNotifier(_make_config())
            assert notifier.enabled

    async def test_send_noop_when_disabled(self):
        """Sending on a disabled notifier is a silent no-op."""
        with patch.dict(os.environ, {}, clear=True):
            notifier = TelegramNotifier(_make_config())
            # Should not raise
            await notifier.send("hello")

    async def test_send_calls_telegram_api(self):
        """Sends a message via the Telegram Bot API."""
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "42"}):
            notifier = TelegramNotifier(_make_config())

        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("tasks._notifier.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await notifier.send("test message")

            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert "/sendMessage" in call_args[0][0]
            assert call_args[1]["json"]["chat_id"] == "42"
            assert call_args[1]["json"]["text"] == "test message"

    async def test_send_document(self, tmp_path):
        """Sends a file attachment via sendDocument."""
        test_file = tmp_path / "report.pdf"
        test_file.write_bytes(b"fake pdf content")

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "42"}):
            notifier = TelegramNotifier(_make_config())

        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("tasks._notifier.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await notifier.send("msg", attachments=[test_file])

            assert mock_client.post.call_count == 2
            send_doc_call = mock_client.post.call_args_list[1]
            assert "/sendDocument" in send_doc_call[0][0]

    async def test_skips_large_files(self, tmp_path):
        """Files exceeding max_attachment_size_mb are skipped."""
        test_file = tmp_path / "huge.bin"
        test_file.write_bytes(b"x" * 100)

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "42"}):
            # Set max to 0 MB so the 100-byte file exceeds it
            notifier = TelegramNotifier(_make_config(max_attachment_size_mb=0))

        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("tasks._notifier.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await notifier.send("msg", attachments=[test_file])

            # Only sendMessage, no sendDocument
            assert mock_client.post.call_count == 1

    async def test_send_does_not_raise_on_error(self):
        """Errors in send are logged, never raised."""
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "42"}):
            notifier = TelegramNotifier(_make_config())

        with patch("tasks._notifier.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = ConnectionError("offline")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            # Should not raise
            await notifier.send("test")


@pytest.mark.unit
class TestMessageFormatting:
    """Test notification message formatting."""

    def test_format_run_completed(self):
        """Success message includes goal name, stats, output, and file count."""
        msg = format_run_completed(
            goal_description="Find Pop-Tarts prices",
            run_number=2,
            duration="47s",
            total_tasks=3,
            completed_tasks=3,
            final_output="Walmart: $3.48",
            file_count=1,
        )
        assert "Find Pop-Tarts prices" in msg
        assert "Run #2" in msg
        assert "3/3" in msg
        assert "Walmart: $3.48" in msg
        assert "1 file attached" in msg

    def test_format_run_completed_no_files(self):
        """Success message omits file line when no files."""
        msg = format_run_completed(
            goal_description="Test",
            run_number=1,
            duration="5s",
            total_tasks=1,
            completed_tasks=1,
            final_output="done",
            file_count=0,
        )
        assert "file" not in msg

    def test_format_run_failed(self):
        """Failure message includes error details."""
        msg = format_run_failed(
            goal_description="Scrape data",
            run_number=1,
            duration="12s",
            total_tasks=3,
            completed_tasks=1,
            failed_task_description="Fetch page",
            error="ConnectionError: timeout",
        )
        assert "Scrape data" in msg
        assert "1/3" in msg
        assert "Fetch page" in msg
        assert "ConnectionError" in msg
