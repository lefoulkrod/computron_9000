"""Tests for server._settings_routes settings persistence."""

import json

import pytest

from server._settings_routes import load_settings, save_settings, _settings_path


@pytest.fixture(autouse=True)
def _isolate_settings(tmp_path, monkeypatch):
    """Point settings at a temp directory."""
    monkeypatch.setattr(
        "server._settings_routes._settings_path",
        lambda: tmp_path / "settings.json",
    )


@pytest.mark.unit
class TestLoadSettings:
    """Loading settings from disk."""

    def test_defaults_when_missing(self):
        """Returns defaults when file doesn't exist."""
        s = load_settings()
        assert s["setup_complete"] is False
        assert s["default_agent"] == "computron"
        assert s["vision_model"] == ""
        assert s["compaction_model"] == ""

    def test_loads_from_disk(self, tmp_path):
        """Reads saved settings."""
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({
            "setup_complete": True,
            "default_agent": "code_expert",
            "vision_model": "gemma3:12b",
            "compaction_model": "kimi-k2.5:cloud",
        }))
        s = load_settings()
        assert s["setup_complete"] is True
        assert s["default_agent"] == "code_expert"
        assert s["vision_model"] == "gemma3:12b"


@pytest.mark.unit
class TestSaveSettings:
    """Saving settings to disk."""

    def test_creates_file(self, tmp_path):
        """Creates settings file if it doesn't exist."""
        result = save_settings({"setup_complete": True})
        assert result["setup_complete"] is True
        path = tmp_path / "settings.json"
        assert path.exists()

    def test_merges_with_existing(self, tmp_path):
        """Partial update merges with existing settings."""
        save_settings({"setup_complete": True, "vision_model": "gemma3:12b"})
        result = save_settings({"default_agent": "research_agent"})
        assert result["setup_complete"] is True
        assert result["vision_model"] == "gemma3:12b"
        assert result["default_agent"] == "research_agent"

    def test_overwrites_existing_key(self):
        """Setting an existing key overwrites it."""
        save_settings({"vision_model": "old"})
        result = save_settings({"vision_model": "new"})
        assert result["vision_model"] == "new"
