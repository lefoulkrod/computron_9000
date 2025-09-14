"""Project-wide pytest fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _reset_shutdown_registry_between_tests():
    """Reset the global shutdown registry before and after each test.

    This keeps tests isolated without relying on production-only test helpers.
    """
    try:
        # Import the module and mutate private state under its lock.
        import utils.shutdown as _shutdown

        with _shutdown._lock:  # type: ignore[attr-defined]
            _shutdown._handlers.clear()  # type: ignore[attr-defined]
            _shutdown._names.clear()  # type: ignore[attr-defined]
            _shutdown._ran = False  # type: ignore[attr-defined]
    except Exception:
        # If the module isn't present or can't be manipulated, skip silently.
        return
    yield
    try:
        with _shutdown._lock:  # type: ignore[name-defined, attr-defined]
            _shutdown._handlers.clear()  # type: ignore[attr-defined]
            _shutdown._names.clear()  # type: ignore[attr-defined]
            _shutdown._ran = False  # type: ignore[attr-defined]
    except Exception:
        # Don't fail teardown if cleanup can't run.
        pass
