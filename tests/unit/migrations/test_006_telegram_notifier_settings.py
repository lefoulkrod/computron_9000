"""Tests for migration 006: Telegram notifier keys seeded into settings.json."""

import json

import pytest

from migrations._006_telegram_notifier_settings import migrate


@pytest.fixture()
def state_dir(tmp_path):
    """State directory root."""
    return tmp_path


@pytest.mark.unit
def test_no_settings_file_is_noop(state_dir):
    """Install without a settings.json does nothing — defaults apply on read."""
    migrate(state_dir)
    assert not (state_dir / "settings.json").exists()


@pytest.mark.unit
def test_seeds_missing_fields(state_dir):
    """A pre-existing settings.json without notifier fields gets them filled in."""
    path = state_dir / "settings.json"
    path.write_text(json.dumps({"setup_complete": True}))

    migrate(state_dir)

    data = json.loads(path.read_text())
    assert data["setup_complete"] is True
    assert data["telegram_notifier_integration_id"] == ""
    assert data["telegram_notifier_chat_id"] is None


@pytest.mark.unit
def test_preserves_existing_values(state_dir):
    """User-set notifier values are not overwritten."""
    path = state_dir / "settings.json"
    path.write_text(json.dumps({
        "telegram_notifier_integration_id": "telegram_personal",
        "telegram_notifier_chat_id": 42,
    }))

    migrate(state_dir)

    data = json.loads(path.read_text())
    assert data["telegram_notifier_integration_id"] == "telegram_personal"
    assert data["telegram_notifier_chat_id"] == 42


@pytest.mark.unit
def test_corrupt_settings_file_is_skipped(state_dir):
    """A corrupt settings.json doesn't raise; it's left alone."""
    path = state_dir / "settings.json"
    path.write_text("{not-json")

    migrate(state_dir)

    assert path.read_text() == "{not-json"
