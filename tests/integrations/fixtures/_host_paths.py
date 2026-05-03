"""Shared host-path scaffolding for supervisor integration tests.

The supervisor's host-path registry is per-deployment; tests build a tmp
registry pointing at ``tmp_path`` so vault and downloads stay isolated.
The helpers here keep that boilerplate out of every test.
"""

from __future__ import annotations

from pathlib import Path

from integrations.supervisor.types import HostPath, HostPathBinding

EMAIL_BROKER_HOST_PATHS: tuple[HostPathBinding, ...] = (
    HostPathBinding(role="downloads", env_var="ATTACHMENTS_DIR", mode="write"),
)


def make_host_paths(tmp_path: Path) -> dict[str, HostPath]:
    """Single-entry registry exposing ``tmp_path / 'attachments'`` as the downloads role."""
    return {
        "downloads": HostPath(
            path=tmp_path / "attachments",
            description="test downloads dir",
            owner="test",
            group="test",
            mode=0o3770,
        ),
    }
