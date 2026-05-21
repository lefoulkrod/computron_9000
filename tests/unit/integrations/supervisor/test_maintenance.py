"""Tests for the supervisor's one-shot maintenance hook."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from integrations._perms import AGENT_OWNED_DIR_MODE, AGENT_OWNED_FILE_MODE
from integrations.supervisor._maintenance import (
    _SENTINEL_FILE,
    _heal_downloads_perms,
    run_pending,
)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode) | (path.stat().st_mode & 0o7000)


def test_heal_chmods_files_and_dirs_owned_by_self(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    sub = downloads / "broker_subdir"
    sub.mkdir()
    f1 = downloads / "old.bin"
    f1.write_bytes(b"hi")
    f2 = sub / "nested.txt"
    f2.write_text("x")
    f1.chmod(0o640)
    f2.chmod(0o600)
    sub.chmod(0o3770)

    n = _heal_downloads_perms(downloads)

    assert n == 3
    assert _mode(f1) == AGENT_OWNED_FILE_MODE
    assert _mode(f2) == AGENT_OWNED_FILE_MODE
    assert _mode(sub) == AGENT_OWNED_DIR_MODE


def test_heal_is_idempotent(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    f = downloads / "already.bin"
    f.write_bytes(b"")
    f.chmod(AGENT_OWNED_FILE_MODE)

    assert _heal_downloads_perms(downloads) == 0


def test_heal_skips_files_owned_by_other_uid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    foreign = downloads / "agent_wrote_this.bin"
    foreign.write_bytes(b"")
    foreign.chmod(0o600)

    # Simulate the file being owned by a different uid by pretending our own
    # uid is something else. We can't actually chown without root.
    fake_uid = os.getuid() + 12345
    monkeypatch.setattr(os, "getuid", lambda: fake_uid)

    assert _heal_downloads_perms(downloads) == 0
    assert _mode(foreign) == 0o600


def test_heal_missing_dir_returns_zero(tmp_path: Path) -> None:
    assert _heal_downloads_perms(tmp_path / "does_not_exist") == 0


def test_run_pending_records_sentinel(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    f = downloads / "f.bin"
    f.write_bytes(b"")
    f.chmod(0o640)

    run_pending(vault, downloads)

    sentinel = vault / _SENTINEL_FILE
    assert sentinel.exists()
    applied = json.loads(sentinel.read_text(encoding="utf-8"))
    assert "heal_downloads_perms_v1" in applied
    assert _mode(f) == AGENT_OWNED_FILE_MODE


def test_run_pending_skips_when_sentinel_set(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / _SENTINEL_FILE).write_text(
        json.dumps(["heal_downloads_perms_v1"]), encoding="utf-8",
    )
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    f = downloads / "still_old.bin"
    f.write_bytes(b"")
    f.chmod(0o640)

    run_pending(vault, downloads)

    # Sentinel said it ran — even though file is still at the old mode.
    assert _mode(f) == 0o640


def test_run_pending_tolerates_missing_downloads(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()

    # No downloads role — nothing to heal, sentinel intentionally not written
    # so the heal can still apply on a future boot once downloads appears.
    run_pending(vault, None)

    assert not (vault / _SENTINEL_FILE).exists()


def test_run_pending_recovers_from_corrupt_sentinel(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / _SENTINEL_FILE).write_text("{not valid json", encoding="utf-8")
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    f = downloads / "f.bin"
    f.write_bytes(b"")
    f.chmod(0o640)

    run_pending(vault, downloads)

    assert _mode(f) == AGENT_OWNED_FILE_MODE
    applied = json.loads((vault / _SENTINEL_FILE).read_text(encoding="utf-8"))
    assert applied == ["heal_downloads_perms_v1"]
