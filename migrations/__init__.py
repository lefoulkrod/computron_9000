"""Data migrations for on-disk state.

Call ``run_migrations(state_dir)`` once at app startup, before the server
begins handling requests. Each migration runs at most once — applied
migrations are tracked in ``{state_dir}/.migrations.json``.
"""

from migrations._runner import run_migrations

__all__ = ["run_migrations"]
