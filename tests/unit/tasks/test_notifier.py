"""Tests for tasks._notifier — Telegram push notifications via the broker."""

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from integrations.broker_client import IntegrationError
from tasks._notifier import (
    TelegramNotifier,
    format_run_completed,
    format_run_failed,
)


def _make_config(**overrides):
    """Build a minimal NotificationsConfig-like object."""
    from config import NotificationsConfig

    return NotificationsConfig(**overrides)


_ENABLED_ENV = {
    "TELEGRAM_INTEGRATION_ID": "telegram_personal",
    "TELEGRAM_CHAT_ID": "42",
}

_APP_SOCK = Path("/tmp/test_app.sock")


@pytest.mark.unit
class TestTelegramNotifier:
    """Test TelegramNotifier init and send behavior."""

    def test_enables_when_env_vars_present(self):
        """Notifier is enabled when both env vars are set."""
        with patch.dict(os.environ, _ENABLED_ENV):
            notifier = TelegramNotifier(_make_config(), app_sock_path=_APP_SOCK)
            assert notifier.enabled

    def test_disabled_when_env_vars_missing(self):
        """Notifier disables itself with a warning when either env is unset."""
        with patch.dict(os.environ, {}, clear=True):
            notifier = TelegramNotifier(_make_config(), app_sock_path=_APP_SOCK)
            assert not notifier.enabled

    def test_disabled_when_chat_id_not_numeric(self):
        """A non-integer chat ID disables the notifier."""
        with patch.dict(
            os.environ,
            {"TELEGRAM_INTEGRATION_ID": "telegram_personal", "TELEGRAM_CHAT_ID": "not-a-number"},
        ):
            notifier = TelegramNotifier(_make_config(), app_sock_path=_APP_SOCK)
            assert not notifier.enabled

    async def test_send_noop_when_disabled(self):
        """Sending on a disabled notifier is a silent no-op (no broker call)."""
        with patch.dict(os.environ, {}, clear=True):
            notifier = TelegramNotifier(_make_config(), app_sock_path=_APP_SOCK)
        with patch("tasks._notifier.broker_call", new_callable=AsyncMock) as mock_call:
            await notifier.send("hello")
            mock_call.assert_not_called()

    async def test_send_calls_broker(self):
        """Sends a message via broker_client.call('send_message', ...)."""
        with patch.dict(os.environ, _ENABLED_ENV):
            notifier = TelegramNotifier(_make_config(), app_sock_path=_APP_SOCK)
        with patch("tasks._notifier.broker_call", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"message_id": 1}

            await notifier.send("test message")

            mock_call.assert_awaited_once_with(
                "telegram_personal",
                "send_message",
                {"chat_id": 42, "text": "test message"},
                app_sock_path=_APP_SOCK,
            )

    async def test_send_truncates_long_messages(self):
        """Messages over the Telegram limit are truncated before sending."""
        with patch.dict(os.environ, _ENABLED_ENV):
            notifier = TelegramNotifier(_make_config(), app_sock_path=_APP_SOCK)
        with patch("tasks._notifier.broker_call", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"message_id": 1}

            await notifier.send("x" * 5000)

            args = mock_call.await_args.args
            sent_text = args[2]["text"]
            assert len(sent_text) <= 4096
            assert sent_text.endswith("… (truncated)")

    async def test_send_skips_attachments_for_now(self, tmp_path):
        """Attachments are logged-and-skipped until broker send_document lands."""
        test_file = tmp_path / "report.pdf"
        test_file.write_bytes(b"fake pdf content")

        with patch.dict(os.environ, _ENABLED_ENV):
            notifier = TelegramNotifier(_make_config(), app_sock_path=_APP_SOCK)
        with patch("tasks._notifier.broker_call", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"message_id": 1}

            await notifier.send("msg", attachments=[test_file])

            # Only the text send_message call; no document call.
            assert mock_call.await_count == 1
            assert mock_call.await_args.args[1] == "send_message"

    async def test_send_does_not_raise_on_broker_error(self):
        """Errors from the broker are logged, never raised."""
        with patch.dict(os.environ, _ENABLED_ENV):
            notifier = TelegramNotifier(_make_config(), app_sock_path=_APP_SOCK)
        with patch(
            "tasks._notifier.broker_call",
            new_callable=AsyncMock,
            side_effect=IntegrationError("broker offline"),
        ):
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
