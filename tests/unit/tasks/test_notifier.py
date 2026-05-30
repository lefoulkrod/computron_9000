"""Tests for tasks._notifier — Telegram push notifications via the broker."""

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


_ENABLED_SETTINGS = {
    "telegram_notifier_integration_id": "telegram_personal",
    "telegram_notifier_chat_id": 42,
}

_APP_SOCK = Path("/tmp/test_app.sock")


def _patch_settings(settings: dict):
    """Patch ``load_settings`` inside the notifier module."""
    return patch("tasks._notifier.load_settings", return_value=settings)


@pytest.mark.unit
def test_enables_when_settings_present():
    """Notifier is enabled when both settings are populated."""
    with _patch_settings(_ENABLED_SETTINGS):
        notifier = TelegramNotifier(_make_config(), app_sock_path=_APP_SOCK)
        assert notifier.enabled


@pytest.mark.unit
def test_disabled_when_settings_blank():
    """Notifier disables itself when integration_id is blank or chat_id is None."""
    with _patch_settings({}):
        notifier = TelegramNotifier(_make_config(), app_sock_path=_APP_SOCK)
        assert not notifier.enabled


@pytest.mark.unit
def test_disabled_when_only_integration_id_set():
    with _patch_settings(
        {"telegram_notifier_integration_id": "telegram_personal", "telegram_notifier_chat_id": None},
    ):
        notifier = TelegramNotifier(_make_config(), app_sock_path=_APP_SOCK)
        assert not notifier.enabled


@pytest.mark.unit
def test_disabled_when_only_chat_id_set():
    with _patch_settings(
        {"telegram_notifier_integration_id": "", "telegram_notifier_chat_id": 42},
    ):
        notifier = TelegramNotifier(_make_config(), app_sock_path=_APP_SOCK)
        assert not notifier.enabled


@pytest.mark.unit
def test_disabled_when_chat_id_not_int():
    """A non-integer chat_id (e.g. stray string) disables the notifier rather than crashing."""
    with _patch_settings(
        {"telegram_notifier_integration_id": "telegram_personal", "telegram_notifier_chat_id": "42"},
    ):
        notifier = TelegramNotifier(_make_config(), app_sock_path=_APP_SOCK)
        assert not notifier.enabled


@pytest.mark.unit
async def test_send_noop_when_disabled():
    """Sending on a disabled notifier is a silent no-op (no broker call)."""
    with _patch_settings({}):
        notifier = TelegramNotifier(_make_config(), app_sock_path=_APP_SOCK)
    with patch("tasks._notifier.broker_call", new_callable=AsyncMock) as mock_call:
        await notifier.send("hello")
        mock_call.assert_not_called()


@pytest.mark.unit
async def test_send_calls_broker():
    """Sends a message via broker_client.call('send_message', ...)."""
    with _patch_settings(_ENABLED_SETTINGS):
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


@pytest.mark.unit
async def test_send_truncates_long_messages():
    """Messages over the Telegram limit are truncated before sending."""
    with _patch_settings(_ENABLED_SETTINGS):
        notifier = TelegramNotifier(_make_config(), app_sock_path=_APP_SOCK)
    with patch("tasks._notifier.broker_call", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {"message_id": 1}

        await notifier.send("x" * 5000)

        args = mock_call.await_args.args
        sent_text = args[2]["text"]
        assert len(sent_text) <= 4096
        assert sent_text.endswith("… (truncated)")


@pytest.mark.unit
async def test_send_skips_attachments_for_now(tmp_path):
    """Attachments are logged-and-skipped until broker send_document lands."""
    test_file = tmp_path / "report.pdf"
    test_file.write_bytes(b"fake pdf content")

    with _patch_settings(_ENABLED_SETTINGS):
        notifier = TelegramNotifier(_make_config(), app_sock_path=_APP_SOCK)
    with patch("tasks._notifier.broker_call", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {"message_id": 1}

        await notifier.send("msg", attachments=[test_file])

        # Only the text send_message call; no document call.
        assert mock_call.await_count == 1
        assert mock_call.await_args.args[1] == "send_message"


@pytest.mark.unit
async def test_send_does_not_raise_on_broker_error():
    """Errors from the broker are logged, never raised."""
    with _patch_settings(_ENABLED_SETTINGS):
        notifier = TelegramNotifier(_make_config(), app_sock_path=_APP_SOCK)
    with patch(
        "tasks._notifier.broker_call",
        new_callable=AsyncMock,
        side_effect=IntegrationError("broker offline"),
    ):
        # Should not raise
        await notifier.send("test")


@pytest.mark.unit
def test_format_run_completed():
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


@pytest.mark.unit
def test_format_run_completed_no_files():
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


@pytest.mark.unit
def test_format_run_failed():
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
