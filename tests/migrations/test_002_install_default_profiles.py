"""Tests for migration 002: install default agent profiles."""

import json

import pytest

from migrations._002_install_default_profiles import _DEFAULT_PROFILES_DIR, migrate


@pytest.fixture()
def state_dir(tmp_path):
    """Create a state directory."""
    return tmp_path


@pytest.mark.unit
class TestMigration002:
    """Installation of default agent profiles."""

    def test_installs_all_defaults(self, state_dir):
        """All shipped profiles are copied to the state directory."""
        migrate(state_dir)
        dest = state_dir / "agent_profiles"
        expected = {f.name for f in _DEFAULT_PROFILES_DIR.glob("*.json")}
        actual = {f.name for f in dest.glob("*.json")}
        assert actual == expected

    def test_does_not_overwrite_existing(self, state_dir):
        """Profiles that already exist on disk are not overwritten."""
        dest = state_dir / "agent_profiles"
        dest.mkdir(parents=True)
        # Write a custom version of computron.json
        custom = {"id": "computron", "name": "My Custom Computron", "description": "custom"}
        (dest / "computron.json").write_text(json.dumps(custom))

        migrate(state_dir)

        # The custom version should be preserved
        data = json.loads((dest / "computron.json").read_text())
        assert data["name"] == "My Custom Computron"

    def test_creates_profiles_dir(self, state_dir):
        """The agent_profiles directory is created if it doesn't exist."""
        assert not (state_dir / "agent_profiles").exists()
        migrate(state_dir)
        assert (state_dir / "agent_profiles").is_dir()

    def test_idempotent(self, state_dir):
        """Running the migration twice produces the same result."""
        migrate(state_dir)
        first = {
            f.name: f.read_text()
            for f in (state_dir / "agent_profiles").glob("*.json")
        }
        migrate(state_dir)
        second = {
            f.name: f.read_text()
            for f in (state_dir / "agent_profiles").glob("*.json")
        }
        assert first == second

    def test_valid_json(self, state_dir):
        """All installed profiles are valid JSON with required fields."""
        migrate(state_dir)
        for f in (state_dir / "agent_profiles").glob("*.json"):
            data = json.loads(f.read_text())
            assert "id" in data, f"Missing 'id' in {f.name}"
            assert "name" in data, f"Missing 'name' in {f.name}"
