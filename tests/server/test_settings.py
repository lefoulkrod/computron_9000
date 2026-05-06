"""Tests for settings persistence and SettingsUpdate validation."""

import json

import pytest
from pydantic import ValidationError

from settings import SettingsUpdate, load_settings, save_settings


@pytest.fixture(autouse=True)
def _isolate_settings(tmp_path, monkeypatch):
    """Point settings at a temp directory."""
    monkeypatch.setattr(
        "settings._settings_path",
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

    def test_atomic_write_produces_valid_json(self, tmp_path):
        """Written file is valid JSON (atomic rename guarantees partial writes don't exist)."""
        save_settings({"setup_complete": True, "vision_model": "test-model"})
        path = tmp_path / "settings.json"
        content = json.loads(path.read_text())
        assert content["setup_complete"] is True
        assert content["vision_model"] == "test-model"


@pytest.mark.unit
class TestSettingsUpdate:
    """SettingsUpdate Pydantic model validation."""

    def test_known_keys_accepted(self):
        u = SettingsUpdate(setup_complete=True, default_agent="computron")
        assert u.setup_complete is True
        assert u.default_agent == "computron"

    def test_unknown_key_raises(self):
        """Extra keys must be rejected (extra='forbid')."""
        with pytest.raises(ValidationError, match="Extra inputs"):
            SettingsUpdate(unknown_setting="value")

    def test_llm_fields_accepted(self):
        u = SettingsUpdate(
            llm_provider="openai",
            llm_base_url="http://localhost:1234/v1",
        )
        assert u.llm_provider == "openai"
        assert u.llm_base_url == "http://localhost:1234/v1"

    def test_llm_api_key_rejected(self):
        """llm_api_key is no longer a settings field — keys live in the vault."""
        with pytest.raises(ValidationError, match="Extra inputs"):
            SettingsUpdate(llm_api_key="sk-test")

    def test_llm_base_url_rejects_non_http_scheme(self):
        """file:// and other dangerous schemes must be rejected."""
        with pytest.raises(ValidationError, match="http or https"):
            SettingsUpdate(llm_base_url="file:///etc/passwd")

    def test_llm_base_url_rejects_gopher(self):
        with pytest.raises(ValidationError, match="http or https"):
            SettingsUpdate(llm_base_url="gopher://evil.example.com")

    def test_llm_base_url_rejects_metadata_ip(self):
        """AWS instance metadata IP must be blocked."""
        with pytest.raises(ValidationError, match="blocked"):
            SettingsUpdate(llm_base_url="http://169.254.169.254/latest/meta-data")

    def test_llm_base_url_allows_localhost(self):
        """localhost (used by Ollama) must be allowed."""
        u = SettingsUpdate(llm_base_url="http://localhost:11434")
        assert u.llm_base_url == "http://localhost:11434"

    def test_llm_base_url_allows_https(self):
        u = SettingsUpdate(llm_base_url="https://api.openai.com/v1")
        assert u.llm_base_url == "https://api.openai.com/v1"

    def test_null_vision_model_accepted(self):
        """vision_model: null is the explicit skip value."""
        u = SettingsUpdate(vision_model=None)
        assert u.vision_model is None

    def test_model_fields_set_tracks_provided_fields(self):
        """Only explicitly provided fields appear in model_fields_set."""
        u = SettingsUpdate(setup_complete=True)
        assert "setup_complete" in u.model_fields_set
        assert "vision_model" not in u.model_fields_set

    def test_exclude_unset_omits_defaults(self):
        """model_dump(exclude_unset=True) contains only provided fields."""
        u = SettingsUpdate(vision_model="qwen3.5")
        dumped = u.model_dump(exclude_unset=True)
        assert "vision_model" in dumped
        assert "setup_complete" not in dumped
        assert "llm_provider" not in dumped
