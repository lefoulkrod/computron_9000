"""Tests for migration 005: global LLM provider -> per-use providers."""

import json

import pytest

from agents import PROFILES_SUBDIR
from migrations._005_multi_provider import (
    _LEGACY_COMPACTION_OPTIONS,
    _OLLAMA_DEFAULT_URL,
    migrate,
)


@pytest.fixture()
def state_dir(tmp_path):
    return tmp_path


def _write_settings(state_dir, data):
    (state_dir / "settings.json").write_text(json.dumps(data))


def _read_settings(state_dir):
    return json.loads((state_dir / "settings.json").read_text())


def _write_profile(state_dir, name, data):
    d = state_dir / PROFILES_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps(data))


def _read_profile(state_dir, name):
    return json.loads((state_dir / PROFILES_SUBDIR / f"{name}.json").read_text())


@pytest.mark.unit
class TestMigration005Settings:
    def test_no_settings_file_is_noop(self, state_dir):
        migrate(state_dir)
        assert not (state_dir / "settings.json").exists()

    def test_legacy_ollama_converted(self, state_dir):
        _write_settings(state_dir, {
            "setup_complete": True,
            "llm_provider": "ollama",
            "llm_base_url": "http://host:11434",
            "compaction_model": "qwen3:8b",
        })

        migrate(state_dir)

        s = _read_settings(state_dir)
        assert "llm_provider" not in s and "llm_base_url" not in s
        assert s["direct_providers"] == {"ollama": {"base_url": "http://host:11434"}}
        assert s["vision_provider"] == "ollama"
        assert s["compaction_provider"] == "ollama"
        assert s["title_provider"] == "ollama"
        # title_model follows the install's main model, not the old kimi hardcode
        assert s["title_model"] == "qwen3:8b"
        assert s["compaction_options"] == _LEGACY_COMPACTION_OPTIONS

    def test_title_model_left_unset_without_compaction_model(self, state_dir):
        _write_settings(state_dir, {"llm_provider": "anthropic"})
        migrate(state_dir)
        s = _read_settings(state_dir)
        assert s["title_provider"] == "anthropic"
        assert "title_model" not in s

    def test_legacy_ollama_without_base_url_uses_default(self, state_dir):
        _write_settings(state_dir, {"llm_provider": "ollama"})
        migrate(state_dir)
        s = _read_settings(state_dir)
        assert s["direct_providers"] == {"ollama": {"base_url": _OLLAMA_DEFAULT_URL}}

    def test_brokered_provider_gets_no_direct_entry(self, state_dir):
        _write_settings(state_dir, {"llm_provider": "anthropic"})
        migrate(state_dir)
        s = _read_settings(state_dir)
        assert s["direct_providers"] == {}
        assert s["vision_provider"] == "anthropic"
        assert s["compaction_provider"] == "anthropic"
        assert s["title_provider"] == "anthropic"

    def test_existing_per_use_settings_preserved(self, state_dir):
        _write_settings(state_dir, {
            "llm_provider": "ollama",
            "vision_provider": "anthropic",
            "title_model": "custom-title-model",
            "compaction_options": {"num_ctx": 1024},
        })
        migrate(state_dir)
        s = _read_settings(state_dir)
        assert s["vision_provider"] == "anthropic"
        assert s["title_model"] == "custom-title-model"
        assert s["compaction_options"] == {"num_ctx": 1024}
        assert s["compaction_provider"] == "ollama"

    def test_corrupt_settings_file_is_skipped(self, state_dir):
        (state_dir / "settings.json").write_text("{not-json")
        migrate(state_dir)
        assert (state_dir / "settings.json").read_text() == "{not-json"


@pytest.mark.unit
class TestMigration005Profiles:
    def test_stamps_provider_from_legacy_setting(self, state_dir):
        _write_settings(state_dir, {"llm_provider": "openai"})
        _write_profile(state_dir, "a", {"id": "a", "name": "A", "model": "gpt-4"})
        migrate(state_dir)
        assert _read_profile(state_dir, "a")["provider"] == "openai"

    def test_existing_profile_provider_untouched(self, state_dir):
        _write_settings(state_dir, {"llm_provider": "openai"})
        _write_profile(state_dir, "a", {"id": "a", "name": "A", "model": "m", "provider": "anthropic"})
        migrate(state_dir)
        assert _read_profile(state_dir, "a")["provider"] == "anthropic"

    def test_defaults_to_ollama_when_no_settings(self, state_dir):
        _write_profile(state_dir, "a", {"id": "a", "name": "A", "model": "m"})
        migrate(state_dir)
        assert _read_profile(state_dir, "a")["provider"] == "ollama"
