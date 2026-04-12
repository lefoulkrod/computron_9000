"""Tests for the migration runner."""

import json

import pytest

from migrations._runner import _load_applied, _save_applied, run_migrations


@pytest.mark.unit
class TestMigrationRunner:
    """Tests for the migration runner infrastructure."""

    def test_no_state_dir_is_noop(self, tmp_path):
        """Runner does nothing if state directory doesn't exist."""
        run_migrations(tmp_path / "nonexistent")

    def test_empty_state_dir_runs_migrations(self, tmp_path):
        """Runner executes pending migrations on empty state dir."""
        (tmp_path / "goals").mkdir()
        run_migrations(tmp_path)
        applied = _load_applied(tmp_path)
        assert "001_task_agent_to_profile" in applied
        assert "002_install_default_profiles" in applied

    def test_already_applied_skipped(self, tmp_path):
        """Migrations already in .migrations.json are not re-run."""
        (tmp_path / "goals").mkdir()
        # Mark all current migrations as applied
        all_names = {"001_task_agent_to_profile", "002_install_default_profiles"}
        _save_applied(tmp_path, all_names)
        run_migrations(tmp_path)
        applied = _load_applied(tmp_path)
        assert applied == all_names

    def test_applied_file_persists(self, tmp_path):
        """Applied migrations are saved to .migrations.json."""
        (tmp_path / "goals").mkdir()
        run_migrations(tmp_path)
        raw = json.loads((tmp_path / ".migrations.json").read_text())
        assert "001_task_agent_to_profile" in raw
