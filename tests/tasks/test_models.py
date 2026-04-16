"""Tests for tasks._models."""

import pytest

from tasks._models import Goal, Run, Task, TaskResult, _new_id, _utcnow


@pytest.mark.unit
class TestModels:
    """Pydantic model validation and serialization."""

    def test_goal_defaults(self):
        """Goal gets an ID and created_at automatically."""
        g = Goal(description="test goal")
        assert g.id
        assert g.created_at
        assert g.status == "active"
        assert g.cron is None

    def test_goal_with_cron(self):
        """Goal with cron expression."""
        g = Goal(description="recurring", cron="0 */2 * * *")
        assert g.cron == "0 */2 * * *"

    def test_task_defaults(self):
        """Task gets sensible defaults."""
        t = Task(goal_id="g1", description="do thing", instruction="prompt")
        assert t.agent_profile is None
        assert t.depends_on == []
        assert t.max_retries == 3

    def test_task_with_deps(self):
        """Task with dependencies."""
        t = Task(
            goal_id="g1", description="step 2", instruction="prompt",
            depends_on=["t1", "t2"],
        )
        assert t.depends_on == ["t1", "t2"]

    def test_run_defaults(self):
        """Run starts as pending."""
        r = Run(goal_id="g1")
        assert r.status == "pending"
        assert r.started_at is None
        assert r.completed_at is None

    def test_task_result_defaults(self):
        """TaskResult starts as pending with zero retries."""
        tr = TaskResult(run_id="r1", task_id="t1")
        assert tr.status == "pending"
        assert tr.retry_count == 0
        assert tr.result is None

    def test_model_dump_roundtrip(self):
        """Models can be serialized and deserialized."""
        g = Goal(description="test")
        data = g.model_dump()
        g2 = Goal(**data)
        assert g2.id == g.id
        assert g2.description == g.description

    def test_new_id_unique(self):
        """IDs are unique."""
        ids = {_new_id() for _ in range(100)}
        assert len(ids) == 100

    def test_utcnow_format(self):
        """Timestamps are ISO format."""
        ts = _utcnow()
        assert "T" in ts
