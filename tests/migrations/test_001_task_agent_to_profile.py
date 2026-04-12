"""Tests for migration 001: task agent → agent_profile."""

import json

import pytest

from migrations._001_task_agent_to_profile import migrate


def _write_goal(goals_dir, goal_id, tasks):
    """Write a goal file with the given tasks."""
    path = goals_dir / f"{goal_id}.json"
    data = {
        "id": goal_id,
        "description": "test goal",
        "status": "active",
        "tasks": tasks,
    }
    path.write_text(json.dumps(data, indent=2))
    return path


def _read_tasks(goal_path):
    """Read tasks from a goal file."""
    return json.loads(goal_path.read_text())["tasks"]


@pytest.fixture()
def state_dir(tmp_path):
    """Create a state directory with a goals subdirectory."""
    (tmp_path / "goals").mkdir()
    return tmp_path


@pytest.mark.unit
class TestMigration001:
    """Migration of legacy task agent field to agent_profile."""

    def test_browser_maps_to_research_agent(self, state_dir):
        """Legacy agent='browser' maps to agent_profile='research_agent'."""
        goal_path = _write_goal(state_dir / "goals", "g1", [{
            "id": "t1", "goal_id": "g1",
            "description": "browse", "instruction": "go",
            "agent": "browser", "depends_on": [],
        }])
        migrate(state_dir)
        tasks = _read_tasks(goal_path)
        assert tasks[0]["agent_profile"] == "research_agent"
        assert "agent" not in tasks[0]

    def test_coder_maps_to_code_expert(self, state_dir):
        """Legacy agent='coder' maps to agent_profile='code_expert'."""
        goal_path = _write_goal(state_dir / "goals", "g1", [{
            "id": "t1", "goal_id": "g1",
            "description": "code", "instruction": "write",
            "agent": "coder", "depends_on": [],
        }])
        migrate(state_dir)
        tasks = _read_tasks(goal_path)
        assert tasks[0]["agent_profile"] == "code_expert"
        assert "agent" not in tasks[0]

    def test_computron_maps_to_none(self, state_dir):
        """Legacy agent='computron' is removed with no agent_profile set."""
        goal_path = _write_goal(state_dir / "goals", "g1", [{
            "id": "t1", "goal_id": "g1",
            "description": "general", "instruction": "do",
            "agent": "computron", "depends_on": [],
        }])
        migrate(state_dir)
        tasks = _read_tasks(goal_path)
        assert "agent" not in tasks[0]
        assert "agent_profile" not in tasks[0]

    def test_strips_skills_field(self, state_dir):
        """Legacy 'skills' field is removed."""
        goal_path = _write_goal(state_dir / "goals", "g1", [{
            "id": "t1", "goal_id": "g1",
            "description": "old", "instruction": "do",
            "skills": ["browser"], "depends_on": [],
        }])
        migrate(state_dir)
        tasks = _read_tasks(goal_path)
        assert "skills" not in tasks[0]

    def test_strips_agent_config(self, state_dir):
        """Legacy 'agent_config' field is removed."""
        goal_path = _write_goal(state_dir / "goals", "g1", [{
            "id": "t1", "goal_id": "g1",
            "description": "custom", "instruction": "do",
            "agent_config": {"system_prompt": "hi"}, "depends_on": [],
        }])
        migrate(state_dir)
        tasks = _read_tasks(goal_path)
        assert "agent_config" not in tasks[0]

    def test_preserves_existing_agent_profile(self, state_dir):
        """Already-migrated tasks keep their agent_profile."""
        goal_path = _write_goal(state_dir / "goals", "g1", [{
            "id": "t1", "goal_id": "g1",
            "description": "task", "instruction": "inst",
            "agent_profile": "code_expert", "depends_on": [],
        }])
        migrate(state_dir)
        tasks = _read_tasks(goal_path)
        assert tasks[0]["agent_profile"] == "code_expert"

    def test_backup_created(self, state_dir):
        """Migration creates a backup of modified goal files."""
        _write_goal(state_dir / "goals", "g1", [{
            "id": "t1", "goal_id": "g1",
            "description": "browse", "instruction": "go",
            "agent": "browser", "depends_on": [],
        }])
        migrate(state_dir)
        backup = state_dir / "goals" / "g1.pre_migration_001.json"
        assert backup.exists()
        # Backup should contain the original agent field
        backup_tasks = json.loads(backup.read_text())["tasks"]
        assert backup_tasks[0]["agent"] == "browser"

    def test_no_backup_when_unchanged(self, state_dir):
        """No backup is created if the file doesn't need migration."""
        _write_goal(state_dir / "goals", "g1", [{
            "id": "t1", "goal_id": "g1",
            "description": "task", "instruction": "inst",
            "agent_profile": "code_expert", "depends_on": [],
        }])
        migrate(state_dir)
        backup = state_dir / "goals" / "g1.pre_migration_001.json"
        assert not backup.exists()

    def test_idempotent(self, state_dir):
        """Running the migration twice produces the same result."""
        goal_path = _write_goal(state_dir / "goals", "g1", [{
            "id": "t1", "goal_id": "g1",
            "description": "browse", "instruction": "go",
            "agent": "browser", "depends_on": [],
        }])
        migrate(state_dir)
        first_result = _read_tasks(goal_path)
        migrate(state_dir)
        second_result = _read_tasks(goal_path)
        assert first_result == second_result

    def test_no_goals_dir_is_noop(self, tmp_path):
        """Migration does nothing if goals directory doesn't exist."""
        migrate(tmp_path)  # Should not raise

    def test_multiple_tasks_mixed(self, state_dir):
        """A goal with a mix of legacy and current tasks migrates correctly."""
        goal_path = _write_goal(state_dir / "goals", "g1", [
            {
                "id": "t1", "goal_id": "g1",
                "description": "browse", "instruction": "go",
                "agent": "browser", "depends_on": [],
            },
            {
                "id": "t2", "goal_id": "g1",
                "description": "current", "instruction": "do",
                "agent_profile": "code_expert", "depends_on": ["t1"],
            },
        ])
        migrate(state_dir)
        tasks = _read_tasks(goal_path)
        assert tasks[0]["agent_profile"] == "research_agent"
        assert "agent" not in tasks[0]
        assert tasks[1]["agent_profile"] == "code_expert"
