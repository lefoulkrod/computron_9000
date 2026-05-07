"""Tests for migration 003: vision inference options move into settings.json."""

import json

import pytest

from migrations._003_vision_settings import (
    _LEGACY_VISION_OPTIONS,
    _LEGACY_VISION_THINK,
    migrate,
)


@pytest.fixture()
def state_dir(tmp_path):
    """State directory root."""
    return tmp_path


@pytest.mark.unit
class TestMigration003:
    """Seeding of vision_think / vision_options into settings.json."""

    def test_no_settings_file_is_noop(self, state_dir):
        """Install without a settings.json does nothing — defaults apply on read."""
        migrate(state_dir)
        assert not (state_dir / "settings.json").exists()

    def test_seeds_missing_fields(self, state_dir):
        """A pre-existing settings.json without vision fields gets them filled in."""
        path = state_dir / "settings.json"
        path.write_text(json.dumps({"setup_complete": True, "vision_model": "foo"}))

        migrate(state_dir)

        data = json.loads(path.read_text())
        assert data["setup_complete"] is True
        assert data["vision_model"] == "foo"
        assert data["vision_think"] == _LEGACY_VISION_THINK
        assert data["vision_options"] == _LEGACY_VISION_OPTIONS

    def test_preserves_existing_vision_think(self, state_dir):
        """A user-set vision_think is not overwritten."""
        path = state_dir / "settings.json"
        path.write_text(json.dumps({"vision_think": True}))

        migrate(state_dir)

        data = json.loads(path.read_text())
        assert data["vision_think"] is True
        assert data["vision_options"] == _LEGACY_VISION_OPTIONS

    def test_preserves_existing_vision_options(self, state_dir):
        """User-customized vision_options are not overwritten."""
        custom = {"temperature": 0.9}
        path = state_dir / "settings.json"
        path.write_text(json.dumps({"vision_options": custom}))

        migrate(state_dir)

        data = json.loads(path.read_text())
        assert data["vision_options"] == custom
        assert data["vision_think"] == _LEGACY_VISION_THINK

    def test_corrupt_settings_file_is_skipped(self, state_dir):
        """A corrupt settings.json doesn't raise; it's left alone."""
        path = state_dir / "settings.json"
        path.write_text("{not-json")

        migrate(state_dir)

        assert path.read_text() == "{not-json"
