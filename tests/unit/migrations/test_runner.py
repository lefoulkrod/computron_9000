"""Tests for the migration runner.

Runner-level tests only — the actual migrations (001/002/003) are stubbed
with recording lambdas so the assertions don't go stale every time a new
migration lands. Per-migration correctness is its own concern, tested
elsewhere if needed.
"""

import json

import pytest

from migrations._runner import _load_applied, _save_applied, run_migrations


@pytest.mark.unit
def test_no_state_dir_is_noop(tmp_path, monkeypatch):
    """Runner does nothing if the state directory doesn't exist —
    not even loading the migration list."""
    calls: list[str] = []
    monkeypatch.setattr(
        "migrations._runner._MIGRATIONS",
        [("a", lambda _d: calls.append("a"))],
    )
    run_migrations(tmp_path / "nonexistent")
    assert calls == []


@pytest.mark.unit
def test_runs_pending_migrations_in_declared_order(tmp_path, monkeypatch):
    """All migrations run when the applied set is empty, and they
    run in the order declared in ``_MIGRATIONS`` — not alphabetically,
    not in parallel."""
    calls: list[str] = []
    monkeypatch.setattr(
        "migrations._runner._MIGRATIONS",
        [
            ("a", lambda _d: calls.append("a")),
            ("b", lambda _d: calls.append("b")),
            ("c", lambda _d: calls.append("c")),
        ],
    )
    run_migrations(tmp_path)
    assert calls == ["a", "b", "c"]


@pytest.mark.unit
def test_skips_already_applied(tmp_path, monkeypatch):
    """Migrations whose names are in the applied set are not invoked.
    Pending ones still run."""
    calls: list[str] = []
    monkeypatch.setattr(
        "migrations._runner._MIGRATIONS",
        [
            ("a", lambda _d: calls.append("a")),
            ("b", lambda _d: calls.append("b")),
            ("c", lambda _d: calls.append("c")),
        ],
    )
    _save_applied(tmp_path, {"a", "b"})
    run_migrations(tmp_path)
    assert calls == ["c"]
    assert _load_applied(tmp_path) == {"a", "b", "c"}


@pytest.mark.unit
def test_running_twice_is_idempotent(tmp_path, monkeypatch):
    """Two consecutive runs leave the applied set unchanged and don't
    re-invoke any migration on the second pass — the property a user
    relies on every time the app boots."""
    calls: list[str] = []
    monkeypatch.setattr(
        "migrations._runner._MIGRATIONS",
        [
            ("a", lambda _d: calls.append("a")),
            ("b", lambda _d: calls.append("b")),
        ],
    )
    run_migrations(tmp_path)
    applied_first = _load_applied(tmp_path)
    run_migrations(tmp_path)
    applied_second = _load_applied(tmp_path)
    assert calls == ["a", "b"]
    assert applied_first == applied_second == {"a", "b"}


@pytest.mark.unit
def test_applied_file_persists_to_disk(tmp_path, monkeypatch):
    """After a successful run, ``.migrations.json`` on disk reflects
    every migration that was invoked. The runner doesn't keep state
    in memory only — a crash mid-run still records prior successes."""
    monkeypatch.setattr(
        "migrations._runner._MIGRATIONS",
        [
            ("a", lambda _d: None),
            ("b", lambda _d: None),
        ],
    )
    run_migrations(tmp_path)
    raw = json.loads((tmp_path / ".migrations.json").read_text())
    assert set(raw) == {"a", "b"}


@pytest.mark.unit
def test_partial_failure_records_prior_successes(tmp_path, monkeypatch):
    """If a migration raises, the runner stops — but every migration
    that succeeded before the failure is still recorded as applied,
    so a fixed re-run picks up where it left off rather than re-running
    already-completed work."""
    def _bang(_d):
        msg = "boom"
        raise RuntimeError(msg)

    monkeypatch.setattr(
        "migrations._runner._MIGRATIONS",
        [
            ("a", lambda _d: None),
            ("b", _bang),
            ("c", lambda _d: None),
        ],
    )
    with pytest.raises(RuntimeError, match="boom"):
        run_migrations(tmp_path)
    # 'a' completed, 'b' raised, 'c' never ran.
    assert _load_applied(tmp_path) == {"a"}
